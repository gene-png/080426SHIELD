"""Read values out of the web bundle's `assessment-targets.ts`, for the
cross-language parity tests (#422).

The api container mounts that ONE file read-only at `/web-parity/`, and a CI
checkout has it in place (`tests/_paths.py::find_web_assessment_targets`).

**A LOCAL GREEN FROM A LONG-RUNNING CONTAINER IS NOT EVIDENCE.** A single-file
bind mount pins the file's inode, so after a branch checkout or an editor's
rename-on-save the container can go on reading the OLD content, and a parity
test then passes against a file that no longer exists on disk. CI's fresh
checkout is the evidence. Locally, recreate the api container (or use
`docker compose run --rm --no-deps api`) before trusting a green.

Everything here FAILS CLOSED: a file it cannot find, a declaration it cannot
find, or a value that is not a plain literal is a hard `pytest.fail`, never a
skip and never a guess. A parity check that skipped where it could not look
would be green exactly where nobody looked.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests._paths import WEB_PARITY_TARGETS, find_web_assessment_targets


def web_targets_source(start: Path) -> str:
    """The text of `assessment-targets.ts`, or a hard failure naming the mount."""
    found = find_web_assessment_targets(start)
    if found is None:
        pytest.fail(
            "apps/web/src/lib/assessment-targets.ts is not readable: no checkout "
            f"above this file and nothing at {WEB_PARITY_TARGETS}. The api service "
            "mounts it there read-only (docker-compose.yml); recreate the api "
            "container if the mount is newer than it. NOT a skip: #422."
        )
    return found.read_text(encoding="utf-8")


def ts_const(source: str, name: str) -> object:
    """The value of a top-level `export const NAME = <number or string>;`.

    Anchored to the START of a line (#794 review, A2): a doc comment quoting
    `export const NAME = …` as an example sits behind ` * `, so it cannot
    match, and the real declaration is the one read.
    """
    m = re.search(rf"^export const {name}\s*=\s*(.+?);", source, re.M | re.S)
    if m is None:
        pytest.fail(f"`export const {name}` not found in assessment-targets.ts")
    raw = m.group(1).strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        pytest.fail(f"`{name}` is not a literal number or string: {raw!r}")
    if not isinstance(value, (int, str)) or isinstance(value, bool):
        pytest.fail(f"`{name}` is not a literal number or string: {raw!r}")
    return value


_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
_BARE_KEY = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*:")
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def ts_object(source: str, name: str) -> dict:
    """A top-level `export const NAME = { … } as const;` whose leaves are
    double-quoted strings, as a dict.

    Prettier writes keys bare when they need no quotes and adds trailing
    commas, so outside string literals bare keys are quoted and trailing
    commas dropped; then it must be JSON, or this fails. The object ends at a
    line that starts with `}` -- the formatter's closing brace.
    """
    m = re.search(
        rf"^export const {name}\s*=\s*(\{{.*?^\}})(?:\s*as const)?;",
        source,
        re.M | re.S,
    )
    if m is None:
        pytest.fail(f"`export const {name} = {{ … }}` not found in assessment-targets.ts")
    body = m.group(1)
    out, pos = [], 0
    for s in _STRING.finditer(body):
        out.append(_TRAILING_COMMA.sub(r"\1", _BARE_KEY.sub(r'"\1":', body[pos : s.start()])))
        out.append(s.group(0))
        pos = s.end()
    out.append(_TRAILING_COMMA.sub(r"\1", _BARE_KEY.sub(r'"\1":', body[pos:])))
    try:
        value = json.loads("".join(out))
    except json.JSONDecodeError as exc:
        pytest.fail(f"`{name}` is not a plain object of string literals: {exc}")
    if not isinstance(value, dict):
        pytest.fail(f"`{name}` is not an object")
    return value
