"""Every Playwright spec on disk must be one CI's E2E run actually includes (#540).

WHY THIS EXISTS. The owner's design for #540's Playwright half: compare the
specs on disk against the specs the CI project runs. `testIgnore`, `testMatch`,
a `grep` in the config or a project filter can drop a spec from the run with
nothing failing -- it simply stops being in the suite. `check_e2e_env_gates.py`
covers the other way a spec never runs (a runtime skip on an unset variable);
this covers exclusion.

HOW. The E2E job runs `npx playwright test --list` with the SAME cwd and
arguments as its real `npx playwright test` step (pinned by a test that parses
ci.yml), writes it to a file, and this compares the spec files named there with
every `*.spec.ts` under `e2e/` (outside `node_modules`). `--list` applies the
config's selection exactly as a run would, without starting a browser or the
stack. Standard library only, because the E2E job installs no Python packages.

LIMITS: `--list` cannot see a test that SKIPS at runtime (that is
`check_e2e_env_gates.py`); and it describes the E2E job's main run, not the
Demo job's `npx playwright test demo/`, which is a subset.

EXIT CODES (D-051): 0 every spec on disk is listed; 1 at least one is not; 2
could not look -- the list file is missing, names no spec, or has no
`Total:` line; no specs on disk; or an unknown argument.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_LISTED = re.compile(r"›\s+(?P<spec>\S+?\.spec\.ts):\d+:\d+")
_TOTAL = re.compile(r"^Total: \d+ tests? in \d+ files?", re.MULTILINE)


class CouldNotLook(Exception):
    """The check could not establish the answer. Maps to exit 2."""


def listed_specs(listing: str) -> set[str]:
    if not _TOTAL.search(listing):
        raise CouldNotLook("no `Total: N tests in M files` line -- not a playwright --list output")
    specs = {m.group("spec").replace("\\", "/") for m in _LISTED.finditer(listing)}
    if not specs:
        raise CouldNotLook("the listing names no spec file; an empty list is not a clean one")
    return specs


def disk_specs(root: Path) -> set[str]:
    e2e = root / "e2e"
    if not e2e.is_dir():
        raise CouldNotLook(f"{e2e} does not exist -- wrong root?")
    specs = {
        p.relative_to(e2e).as_posix()
        for p in e2e.rglob("*.spec.ts")
        if "node_modules" not in p.parts
    }
    if not specs:
        raise CouldNotLook(f"no *.spec.ts under {e2e}")
    return specs


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
        on_disk = disk_specs(root)
    except CouldNotLook as exc:
        print(f"check-e2e-spec-listing: could not look -- {exc}")
        return 2

    missing = sorted(on_disk - listed)
    if missing:
        print(f"check-e2e-spec-listing: {len(missing)} spec(s) on disk that CI's run excludes:")
        for spec in missing:
            print(
                f"  e2e/{spec}: not in `npx playwright test --list` -- excluded by the "
                "config (testIgnore / testMatch / grep / project), so it never runs in CI."
            )
        return 1
    print(
        f"check-e2e-spec-listing: clean -- all {len(on_disk)} spec file(s) on disk are in CI's run."
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
