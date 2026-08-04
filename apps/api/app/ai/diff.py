"""'What the AI changed' diff helpers (Work Order C2).

Pure functions used after a Run-AI rerun to show the admin a short list of what
changed versus the prior version (field, old, new), so a reconsider-everything
rerun never silently overwrites human work. Locked rows are excluded by the
caller before diffing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FieldChange:
    field: str
    old: Any
    new: Any


def changed_fields(
    old: Mapping[str, Any],
    new: Mapping[str, Any],
    fields: Sequence[str],
) -> list[FieldChange]:
    """Per-field changes between two row snapshots, for the named fields."""
    out: list[FieldChange] = []
    for f in fields:
        ov = old.get(f)
        nv = new.get(f)
        if ov != nv:
            out.append(FieldChange(field=f, old=ov, new=nv))
    return out


@dataclass(frozen=True)
class RowDiff:
    key: str
    changes: list[FieldChange]


def diff_keyed_rows(
    old_rows: Mapping[str, Mapping[str, Any]],
    new_rows: Mapping[str, Mapping[str, Any]],
    fields: Sequence[str],
    *,
    locked_keys: frozenset[str] = frozenset(),
) -> list[RowDiff]:
    """Diff two row maps keyed by row id.

    Only rows present in `new_rows` are considered (a rerun re-emits the grid).
    Rows in `locked_keys` are skipped entirely — a locked row is never changed,
    so it never appears in the change list. Returns one RowDiff per row that
    actually changed, sorted by key for stable output.
    """
    diffs: list[RowDiff] = []
    for key in sorted(new_rows):
        if key in locked_keys:
            continue
        old = old_rows.get(key, {})
        changes = changed_fields(old, new_rows[key], fields)
        if changes:
            diffs.append(RowDiff(key=key, changes=changes))
    return diffs
