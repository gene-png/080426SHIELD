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
compose, a YAML 1.2 reader, sees a different value. The node key also records
whether a scalar is PLAIN or QUOTED, because PyYAML's YAML 1.1 tags cannot see
every difference compose's 1.2 reading makes (`"0o17"` versus `0o17`): any
quote flip counts as content. Comments, blank lines and indentation leave the
tree equal. Compose's own `!reset` / `!override` tags are kept, so changing
one is a change.

EXIT CODES (the gates' 0/1/2 convention), three states, and CI's job
"compose content changed" shows them in two colours: 0 UNCHANGED, every
changed compose file parses to the same node tree, or none changed (green);
1 CHANGED, at least one changed in content, and an added or deleted compose
file counts (red); 2 COULD NOT READ, git failed, a file does not parse, or a
bad argument (red). Could-not-read never folds into green. The first line of
output names the state, and the job copies it to its summary.

A change is red on purpose, and rare: of the last 80 first-parent commits on
`main` at ef94f4f (71 of them PR merges; measured 2026-09-25, D-095), two
changed compose content. Red
means a human reads the compose diff, the same design as
`check_merge_rule_text.py`. The job is not a required check.

USAGE: python compose_unchanged.py [--repo DIR] BASE..HEAD
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
            # The STYLE too, plain versus quoted: PyYAML composes `"0o17"` and
            # `0o17` (and `"1e3"` and `1e3`) to the same YAML 1.1 tag and value,
            # while compose, a YAML 1.2 reader, takes the plain forms as numbers.
            return ("s", n.tag, n.value, n.style is None)
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
    try:
        if args[:1] == ["--repo"] and len(args) >= 2:
            repo = Path(args[1])
            args = args[2:]
        if len(args) != 1:
            raise CouldNotLook(
                f"usage: compose_unchanged.py [--repo DIR] BASE..HEAD; got {argv[1:]}"
            )
        changed, form_only = judge(repo, args[0])
    except CouldNotLook as exc:
        print(f"compose content: COULD NOT READ -- {exc}")
        print("  Read as changed: a human reads the compose diff.")
        return 2
    if changed:
        print(f"compose content: CHANGED in {len(changed)} file(s)")
        for name in changed:
            print(f"  content: {name}")
    else:
        print(f"compose content: UNCHANGED ({len(form_only)} file(s) changed in form only)")
    for name in form_only:
        print(f"  form only (comments, layout): {name}")
    if changed:
        return 1
    print("  This says nothing about any path other than the compose files.")
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
