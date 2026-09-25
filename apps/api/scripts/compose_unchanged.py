#!/usr/bin/env python3
"""Does a range change any docker-compose file's PARSED content? (#530, D-095)

The merge rule's one exception to condition 5: a `docker-compose*.yml` diff
whose parsed YAML node tree is unchanged does not trip it. #530's whole
compose diff was comments, and it still came back to the owner. Nothing else
is exempt: every other condition-5 path trips as before, so this answers only
the compose half of the question.

HOW. Each changed `docker-compose*.yml` / `.yaml` at the repo root is composed
at the merge base and at the head, and its NODE tree -- tag and scalar text,
in order -- is compared. Not the loaded object: PyYAML is YAML 1.1 and Python's
`==` is loose, so `on` -> `yes` and `1` -> `1.0` would compare equal while
compose, a YAML 1.2 reader, sees a different value. Comments, blank lines and
quoting style that does not change a tag leave the tree equal. Compose's own
`!reset` / `!override` tags are kept as tags, so changing one is a change.

EXIT CODES (the gates' 0/1/2 convention): 0 every changed compose file parses
to the same node tree, or none changed; 1 at least one changed in content, so
condition 5 trips (an added or deleted compose file counts as changed); 2
could not look -- git failed, a file does not parse, or a bad argument.

`--report` is the CI form (audit-gate.yml's "Compose exception report" job):
it prints the verdict on every PR and exits 0 whether or not a compose file
changed, because a compose content change is a ROUTING fact (condition 5 comes
back to the human), not a defect. It still exits 2 when it could not look, so
the job goes red only then. A green report job therefore means "it looked",
never "condition 5 is clear".

USAGE: python compose_unchanged.py [--report] [--repo DIR] BASE..HEAD
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_COMPOSE = re.compile(r"^docker-compose[^/]*\.ya?ml$")


class CouldNotLook(Exception):
    """The check could not establish the answer. Maps to exit 2."""


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(  # noqa: S603  # nosec B603 - fixed argv
            ["git", "-C", str(repo), *args],  # noqa: S607
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError as exc:
        raise CouldNotLook("`git` is not installed here") from exc
    if proc.returncode != 0:
        raise CouldNotLook(
            f"`git {' '.join(args)}` exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout


def node_tree(src: str, name: str):
    """The composed node tree: (kind, tag, value) all the way down, in order."""
    import yaml

    def key(n):
        if isinstance(n, yaml.ScalarNode):
            return ("s", n.tag, n.value)
        if isinstance(n, yaml.SequenceNode):
            return ("q", n.tag, tuple(key(c) for c in n.value))
        if isinstance(n, yaml.MappingNode):
            return ("m", n.tag, tuple((key(k), key(v)) for k, v in n.value))
        raise CouldNotLook(f"{name}: unexpected YAML node {type(n).__name__}")

    try:
        return tuple(key(doc) for doc in yaml.compose_all(src))
    except yaml.YAMLError as exc:
        raise CouldNotLook(f"{name} does not parse as YAML: {exc}") from exc


def judge(repo: Path, rng: str) -> tuple[list[str], list[str]]:
    """(compose files changed in content, compose files changed only in form)."""
    if ".." not in rng or "..." in rng:
        raise CouldNotLook(f"the range must be BASE..HEAD, got {rng!r}")
    base, head = rng.split("..", 1)
    merge_base = _git(repo, "merge-base", base, head).strip()
    names = [
        n
        for n in _git(
            repo, "diff", "--no-renames", "--name-only", f"{merge_base}..{head}"
        ).splitlines()
        if _COMPOSE.match(n)
    ]
    changed, form_only = [], []
    for name in names:
        old = _show(repo, merge_base, name)
        new = _show(repo, head, name)
        if old is None or new is None:
            changed.append(f"{name} (added or deleted)")
        elif node_tree(old, name) != node_tree(new, name):
            changed.append(name)
        else:
            form_only.append(name)
    return changed, form_only


def _show(repo: Path, ref: str, name: str) -> str | None:
    listed = _git(repo, "ls-tree", "--full-tree", "--name-only", ref, "--", name).strip()
    return _git(repo, "show", f"{ref}:{name}") if listed else None


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = list(argv[1:])
    repo = Path(".")
    report = False
    try:
        if args[:1] == ["--report"]:
            report = True
            args = args[1:]
        if args[:1] == ["--repo"] and len(args) >= 2:
            repo = Path(args[1])
            args = args[2:]
        if len(args) != 1:
            raise CouldNotLook(
                f"usage: compose_unchanged.py [--report] [--repo DIR] BASE..HEAD; got {argv[1:]}"
            )
        changed, form_only = judge(repo, args[0])
    except CouldNotLook as exc:
        print(f"compose-unchanged: could not look -- {exc}")
        print("  Read as TRIPPED: condition 5 comes back to the human.")
        return 2
    for name in form_only:
        print(f"  form only (comments, layout, quoting): {name}")
    if changed:
        print(
            f"compose-unchanged: {len(changed)} compose file(s) changed in CONTENT -- condition 5 trips:"
        )
        for name in changed:
            print(f"  {name}")
        if report:
            print("  (--report: a verdict, not a failure -- the PR comes back to the human.)")
            return 0
        return 1
    print(
        f"compose-unchanged: no compose file changed in content ({len(form_only)} changed in form "
        "only). This says nothing about any OTHER condition-5 path."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"compose-unchanged: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation.{nl}")
        raise SystemExit(2) from exc
