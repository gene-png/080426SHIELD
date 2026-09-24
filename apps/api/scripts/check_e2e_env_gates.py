"""A Playwright spec gated on a variable no workflow sets never runs in CI (#540).

WHY THIS EXISTS. #483: `E2E_PERF` and `E2E_OIDC` gate `test.skip(...)` in two
specs -- one a smoke spec -- and no workflow step sets either, so both have
self-skipped on every CI run while reading as part of the suite. The pytest
half of #540 is `check_ci_selection.py`; whether every spec on disk is in the
set CI runs is `check_e2e_spec_listing.py`. This is the env-gate half.

WHY IT IS STATIC. `npx playwright test --list` lists a self-skipping test as
present: a skip is decided at RUNTIME, so the list cannot see it. What CAN be
seen is the precondition: every environment variable read by a spec that
skips must be SET, to a value that could enable it, by some workflow -- or be
exempted with a reason.

HOW "SET" IS DECIDED. The workflows are PARSED (YAML), never regex-matched as
raw text: a comment such as `# SHIELD_DEMO_SMOKE=1 opts the spec in` is not a
setting, and counting it let a spec that never runs pass (review of e8424dd).
Set means an `env:` key at workflow, job or step level, or an assignment
(`VAR=...` / `export VAR=...`) at the start of a statement in a step's `run:`
script with shell comments stripped -- AND a value that could enable a gate:
empty, "0" and "false" do not count.

THE EXEMPTIONS RATCHET. An exemption for a variable a workflow now sets is
STALE, and so is one no skipping spec reads any more. Both are findings, so
the list only shrinks, and every run prints what it exempts.

WHAT COUNTS AS A SKIPPING SPEC: `test.skip(`, `test.fixme(`,
`test.describe.skip(` / `.fixme(`, and `testInfo.skip(` / `.fixme(`, any
spacing. The variables: `process.env.X`, `process.env["X"]`, and destructuring
`const { X } = process.env`.

LIMITS, stated so a clean run is not read as more than it is:
  * A variable read in an IMPORTED HELPER, not in the spec itself, is unseen.
  * A spec that skips on RUNTIME STATE rather than a variable (s21, s22, s23,
    s32 today) is invisible here.
  * "Set by some workflow" is coarse: set in a different step or job from the
    one that runs the spec still passes. And the exact value the spec needs
    (`=== "1"`) is not checked, only that it is not empty/"0"/"false".
  * A variable that is CONFIGURATION with a default, not a gate
    (E2E_API_URL), is reported unless exempted, because this cannot tell a
    gate from a setting. Exempt it with that reason.

EXIT CODES (D-051): 0 every gate variable is set or exempted; 1 a finding; 2
could not look -- no `e2e/` or no spec files under it, no workflows, a
workflow that does not parse, an unreadable or malformed exemptions file, or
an unknown argument.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

_ENV_DOT = re.compile(r"process\.env\.([A-Z0-9_]+)")
_ENV_INDEX = re.compile(r"""process\.env\[\s*["']([A-Z0-9_]+)["']\s*\]""")
_ENV_DESTRUCTURE = re.compile(r"\{([^{}]*)\}\s*=\s*process\.env\b")
_SKIP = re.compile(r"\b(?:test(?:\s*\.\s*describe)?|testInfo)\s*\.\s*(?:skip|fixme)\s*\(")
_ASSIGN = re.compile(r"^(?:export\s+)?([A-Z0-9_]+)=(\S*)")
_DISABLING = {"", "0", "false"}
EXEMPTIONS = Path(".github/e2e-env-gate-exemptions.json")


class CouldNotLook(Exception):
    """The check could not establish the answer. Maps to exit 2."""


def env_reads(text: str) -> set[str]:
    names = set(_ENV_DOT.findall(text)) | set(_ENV_INDEX.findall(text))
    for group in _ENV_DESTRUCTURE.findall(text):
        for part in group.split(","):
            name = part.split(":")[0].split("=")[0].strip()
            if re.fullmatch(r"[A-Z0-9_]+", name):
                names.add(name)
    return names


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
        if not _SKIP.search(text):
            continue
        rel = spec.relative_to(root).as_posix()
        for var in sorted(env_reads(text)):
            found.setdefault(var, []).append(rel)
    return found


def _unquote(value: object) -> str:
    return str(value).strip().strip("'\"").strip()


def _run_assignments(script: str) -> dict[str, str]:
    """`VAR=value` / `export VAR=value` at the start of a statement, comments stripped."""
    out: dict[str, str] = {}
    for raw in script.splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        for statement in re.split(r"\s*(?:&&|;|\|\|)\s*", line):
            m = _ASSIGN.match(statement.strip())
            if m:
                out[m.group(1)] = _unquote(m.group(2))
    return out


def workflow_settings(root: Path) -> dict[str, set[str]]:
    """{variable: {values}} across every workflow's env blocks and run scripts."""
    wfs = sorted((root / ".github" / "workflows").glob("*.y*ml"))
    if not wfs:
        raise CouldNotLook(f"no workflows under {root / '.github' / 'workflows'}")
    settings: dict[str, set[str]] = {}

    def add(var: str, value: object) -> None:
        settings.setdefault(str(var), set()).add(_unquote(value))

    for wf in wfs:
        try:
            doc = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise CouldNotLook(f"{wf} does not parse: {exc}") from exc
        for k, v in (doc.get("env") or {}).items():
            add(k, v)
        for job in (doc.get("jobs") or {}).values():
            for k, v in (job.get("env") or {}).items():
                add(k, v)
            for step in job.get("steps") or []:
                for k, v in (step.get("env") or {}).items():
                    add(k, v)
                for k, v in _run_assignments(str(step.get("run") or "")).items():
                    add(k, v)
    return settings


def is_set(var: str, settings: dict[str, set[str]]) -> bool:
    return any(v.lower() not in _DISABLING for v in settings.get(var, set()))


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
        settings = workflow_settings(root)
        exemptions = _load_exemptions(root)
    except CouldNotLook as exc:
        print(f"check-e2e-env-gates: could not look -- {exc}")
        return 2

    findings: list[str] = []
    for var, specs in sorted(gates.items()):
        where = ", ".join(specs)
        if var in exemptions:
            if is_set(var, settings):
                findings.append(
                    f"{var}: exemption is STALE -- a workflow now sets it. Remove the exemption."
                )
            else:
                print(f"  exempted: {var} ({where}): {exemptions[var]['reason']}")
        elif not is_set(var, settings):
            findings.append(
                f"{var}: read by {where}, which skips, and NO workflow sets it to a value "
                "that could enable it -- the gated tests never run in CI. Set it in the "
                "step that runs the spec, or exempt it with a reason."
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
