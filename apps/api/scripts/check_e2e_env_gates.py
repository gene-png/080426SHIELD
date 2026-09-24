"""A Playwright spec gated on a variable no workflow sets never runs in CI (#540).

WHY THIS EXISTS. #483: `E2E_PERF` and `E2E_OIDC` gate `test.skip(...)` in two
specs -- one a smoke spec -- and no workflow step sets either, so both have
self-skipped on every CI run while reading as part of the suite. The pytest
half of #540 is `check_ci_selection.py`; this is the Playwright half.

WHY IT IS STATIC. `npx playwright test --list` lists a self-skipping test as
present: a skip is decided at RUNTIME, so the list cannot see it. What CAN be
seen is the precondition: every `process.env.X` read by a spec that calls
`test.skip(` must be set by some workflow, or be exempted with a reason.

THE EXEMPTIONS RATCHET, like the pytest baseline. An exemption for a variable a
workflow now sets is STALE, and so is one no spec reads any more. Both are
findings, so the list only ever shrinks, and every run prints what it exempts.

LIMITS, stated so a clean run is not read as more than it is:
  * A spec that skips on RUNTIME STATE rather than a variable (s21, s22, s23,
    s32 today) is invisible here.
  * "Set by some workflow" is coarse. A variable set in a different step, or a
    different job, from the one that runs the spec passes.
  * A variable that is CONFIGURATION with a default, not a gate (E2E_API_URL),
    is reported unless exempted, because this cannot tell a gate from a
    setting. Exempt it with that reason.

EXIT CODES (D-051): 0 every gate variable is set or exempted; 1 a finding; 2
could not look -- no `e2e/` or no spec files under it, no workflows, an
unreadable or malformed exemptions file, or an unknown argument.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ENV = re.compile(r"process\.env\.([A-Z0-9_]+)")
_SKIP = "test.skip("
EXEMPTIONS = Path(".github/e2e-env-gate-exemptions.json")


class CouldNotLook(Exception):
    """The check could not establish the answer. Maps to exit 2."""


def gate_variables(root: Path) -> dict[str, list[str]]:
    """{variable: [spec paths]} for every env var read by a spec that skips."""
    e2e = root / "e2e"
    if not e2e.is_dir():
        raise CouldNotLook(f"{e2e} does not exist -- wrong directory?")
    specs = [p for p in e2e.rglob("*.spec.ts") if "node_modules" not in p.parts]
    if not specs:
        raise CouldNotLook(f"no *.spec.ts under {e2e}; an empty scan is not a clean one")
    found: dict[str, list[str]] = {}
    for spec in sorted(specs):
        text = spec.read_text(encoding="utf-8")
        if _SKIP not in text:
            continue
        rel = spec.relative_to(root).as_posix()
        for var in sorted(set(_ENV.findall(text))):
            found.setdefault(var, []).append(rel)
    return found


def set_in_workflows(root: Path) -> str:
    wfs = sorted((root / ".github" / "workflows").glob("*.y*ml"))
    if not wfs:
        raise CouldNotLook(f"no workflows under {root / '.github' / 'workflows'}")
    return "\n".join(p.read_text(encoding="utf-8") for p in wfs)


def is_set(var: str, workflows: str) -> bool:
    # A YAML env key (`VAR: "1"`) or a shell assignment (`VAR=1`).
    return bool(re.search(r"(?m)(^|[\s;&|])" + re.escape(var) + r"\s*[:=]", workflows))


def _load_exemptions(root: Path) -> dict[str, dict]:
    path = root / EXEMPTIONS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CouldNotLook(f"cannot read {path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(data, dict) or not all(
        isinstance(v, dict) and str(v.get("reason", "")).strip() for v in data.values()
    ):
        raise CouldNotLook(f"{path}: every entry needs a non-empty `reason`")
    return data


def _parse(argv: list[str]) -> Path:
    root = Path(".")
    args = list(argv[1:])
    while args:
        flag = args.pop(0)
        if flag == "--root" and args:
            root = Path(args.pop(0))
        else:
            raise CouldNotLook(f"unknown or incomplete argument: {flag!r}")
    return root


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        root = _parse(argv)
        gates = gate_variables(root)
        workflows = set_in_workflows(root)
        exemptions = _load_exemptions(root)
    except CouldNotLook as exc:
        print(f"check-e2e-env-gates: could not look -- {exc}")
        return 2

    findings: list[str] = []
    for var, specs in sorted(gates.items()):
        where = ", ".join(specs)
        if var in exemptions:
            if is_set(var, workflows):
                findings.append(
                    f"{var}: exemption is STALE -- a workflow now sets it. Remove the exemption."
                )
            else:
                print(f"  exempted: {var} ({where}): {exemptions[var]['reason']}")
        elif not is_set(var, workflows):
            findings.append(
                f"{var}: read by {where}, which calls test.skip(), and NO workflow sets it -- "
                "the gated tests never run in CI. Set it in the step that runs the spec, "
                "or exempt it with a reason."
            )
    for var in sorted(set(exemptions) - set(gates)):
        findings.append(f"{var}: exemption is STALE -- no skipping spec reads it any more.")

    if findings:
        print(f"check-e2e-env-gates: {len(findings)} finding(s):")
        for line in findings:
            print(f"  {line}")
        return 1
    print(f"check-e2e-env-gates: clean -- {len(gates)} gate variable(s), each set or exempted.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-e2e-env-gates: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(2) from exc
