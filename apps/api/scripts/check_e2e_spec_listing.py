"""Every script-suffixed file under e2e/ must be in CI's E2E run or declared (#540, #579).

WHY THIS EXISTS. The owner's design for #540's Playwright half: compare the
specs on disk against the specs the CI project runs. `testIgnore`, `testMatch`,
a `grep` in the config or a project filter can drop a spec from the run with
nothing failing -- it simply stops being in the suite. `check_e2e_env_gates.py`
covers the other way a spec never runs (a runtime skip on an unset variable);
this covers exclusion.

HOW. The E2E job runs `npx playwright test --list` with the SAME cwd and
arguments as its real `npx playwright test` step (pinned by a test that parses
ci.yml), writes it to a file, and this compares the files named there with
EVERY script file under `e2e/` (any suffix in the name's chain being `.ts`,
`.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.mts` or `.cts`, in any case, outside
`node_modules`). Each must be either in the run or
DECLARED a non-suite file, with a reason, in `.github/e2e-non-suite-files.json`
(helpers, the global setup, the configs, `manual/`). So a spec disabled by a
rename that keeps SOME script suffix in its name -- `a.specs.ts`,
`a.spec.ts.disabled`, `a.spec.TS` -- is reported rather than silently dropped
(#579). A rename that drops every script suffix is not; see LIMITS. A declaration that matches no file, or names a file the run lists, is
a finding too. `--list` applies the config's selection exactly as a run would,
without starting a browser or the stack. Standard library only, because the
E2E job installs no Python packages.

LIMITS: it compares FILES, not tests -- a config `grep`/`grepInvert` that
drops some tests in a file still lists the file, so that file passes. `--list`
cannot see a test that SKIPS at runtime; `check_e2e_env_gates.py` covers only
the skips keyed on an environment variable, so an unconditional `test.skip()`
or `test.describe.skip` is listed, never runs, and neither gate reports it.
It describes the E2E job's main run, not the Demo job's
`npx playwright test demo/`, which is a subset. A declared DIRECTORY
(`helpers/`) covers files added under it that the run does not list: with
`testDir: "."` and no `testIgnore`, a SPEC-NAMED file there is still listed and
so reported as declared-but-listed, but an out-of-pattern name there
(`helpers/s9.specs.ts`) is not reported, and nor would a spec-named one be if
`testIgnore` came to exclude that directory. That declaration's reason is the
only guard there.
Files with no script suffix anywhere in the name are not compared at all, so
a rename that drops the script suffix entirely -- `a.spec.ts~`,
`a.spec.ts_disabled`, `a.spec.ts-old`, `a.spec.txt`, `a.spec` -- takes a spec
out of CI with this gate and the env gate both green (#605). That is the
floor this gate stops at, by decision, rather than listing every file.

EXIT CODES (D-051): 0 every script file on disk is listed or declared; 1 at
least one is neither, or a declaration is stale or names a listed file; 2
could not look -- the list file is missing, names no spec, or has no `Total:`
line; no script files on disk; the declarations file is missing or malformed;
or an unknown argument.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

#: Any extension Playwright's default testMatch can collect, so a listed file is
#: recognised whatever it is called.
_LISTED = re.compile(r"›\s+(?P<spec>\S+?\.[cm]?[jt]sx?):\d+:\d+")
_TOTAL = re.compile(r"^Total: \d+ tests? in \d+ files?", re.MULTILINE)
_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
DECLARATIONS = Path(".github") / "e2e-non-suite-files.json"


class CouldNotLook(Exception):
    """The check could not establish the answer. Maps to exit 2."""


def listed_specs(listing: str) -> set[str]:
    if not _TOTAL.search(listing):
        raise CouldNotLook("no `Total: N tests in M files` line -- not a playwright --list output")
    specs = {m.group("spec").replace("\\", "/") for m in _LISTED.finditer(listing)}
    if not specs:
        raise CouldNotLook("the listing names no spec file; an empty list is not a clean one")
    return specs


def disk_scripts(root: Path) -> set[str]:
    """Every script file under e2e/, relative to it, outside node_modules.

    A file is a script if ANY suffix in its chain is one, case-insensitively:
    a spec disabled by renaming its final suffix (`a.spec.ts.disabled`,
    `.bak`) or its case (`a.spec.TS`) is still a script that is not in the run,
    so it is reported, not skipped as "not a script" (review of 81871d4).
    """
    e2e = root / "e2e"
    if not e2e.is_dir():
        raise CouldNotLook(f"{e2e} does not exist -- wrong root?")
    files = {
        p.relative_to(e2e).as_posix()
        for p in e2e.rglob("*")
        if p.is_file()
        and any(s.lower() in _SUFFIXES for s in p.suffixes)
        and "node_modules" not in p.parts
    }
    if not files:
        raise CouldNotLook(f"no script files under {e2e}")
    return files


def load_declarations(root: Path) -> dict[str, str]:
    """{path or `dir/` prefix, relative to e2e/: reason}. Missing or malformed is 2."""
    path = root / DECLARATIONS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CouldNotLook(f"cannot read {path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip()
        for k, v in data.items()
    ):
        raise CouldNotLook(f"{path}: every entry must map a path to a non-empty reason")
    return data


def _declared_by(path: str, declarations: dict[str, str]) -> str | None:
    for key in declarations:
        if path == key or (key.endswith("/") and path.startswith(key)):
            return key
    return None


def _parse(argv: list[str]) -> tuple[Path, Path]:
    root, listing = Path("."), None
    args = list(argv[1:])
    while args:
        flag = args.pop(0)
        if flag == "--root" and args:
            root = Path(args.pop(0))
        elif flag == "--list-file" and args:
            listing = Path(args.pop(0))
        else:
            raise CouldNotLook(f"unknown or incomplete argument: {flag!r}")
    if listing is None:
        raise CouldNotLook("--list-file is required (the output of `npx playwright test --list`)")
    return root, listing


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        root, listing_path = _parse(argv)
        try:
            listing = listing_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CouldNotLook(f"cannot read {listing_path}: {type(exc).__name__}") from exc
        listed = listed_specs(listing)
        on_disk = disk_scripts(root)
        declarations = load_declarations(root)
    except CouldNotLook as exc:
        print(f"check-e2e-spec-listing: could not look -- {exc}")
        return 2

    findings: list[str] = []
    for path in sorted(on_disk - listed):
        if _declared_by(path, declarations) is None:
            findings.append(
                f"e2e/{path}: not in `npx playwright test --list` and not declared a "
                f"non-suite file -- excluded by the config (testIgnore / testMatch / grep / "
                f"project) or named outside the suite's pattern, so it never runs in CI. "
                f"Fix the name, or declare it in {DECLARATIONS.as_posix()} with a reason."
            )
    for path in sorted(on_disk & listed):
        key = _declared_by(path, declarations)
        if key is not None:
            findings.append(
                f"e2e/{path}: declared a non-suite file ({key!r}) but the run lists it -- "
                "one of the two is wrong."
            )
    for key in sorted(declarations):
        if not any(_declared_by(p, {key: ""}) for p in on_disk):
            findings.append(f"{DECLARATIONS.as_posix()}: {key!r} matches no file -- stale.")
    if findings:
        print(f"check-e2e-spec-listing: {len(findings)} finding(s):")
        for f in findings:
            print(f"  {f}")
        return 1
    print(
        f"check-e2e-spec-listing: clean -- {len(on_disk)} script file(s) under e2e/: "
        f"{len(on_disk & listed)} in CI's run, {len(on_disk - listed)} declared non-suite "
        f"({len(declarations)} declaration(s))."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-e2e-spec-listing: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(2) from exc
