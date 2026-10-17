"""Derive crosswalks X1 and C1 offline (N10, for #1063; track D note rev 5 §12).

X1  SP 800-53 rev5 control -> ATT&CK technique, from MITRE CTID's Mappings
    Explorer (`reference-docs/nist/ctid/`, Apache-2.0), `mitigates` rows only,
    with each ATT&CK 16.1 ID translated to SHIELD's 19.2 catalog through
    `app/integration/data/attack_revocations_19.2.json`.
C1  CSF 2.0 subcategory -> SP 800-53 control -> ATT&CK technique: the "SP 800-53
    Rev 5.1.1" lines of the NIST CSF 2.0 Reference Tool export
    (`reference-docs/nist/csf-2.0-reference-tool-export-2026-10-12.xlsx`)
    composed with X1. Third-party informative references are not read.

Every row keeps its path, so each mapped technique can be explained. Nothing is
dropped silently: every skipped row, untranslated ID and unmatched control is
counted in the output's header, with a reason.

X1 ROWS ARE TRIPLES (control, 19.2 technique, 16.1 source ID): two 16.1 IDs
revoked into one 19.2 technique stay two rows, so `rows` counts triples and
`control_technique_pairs` counts what a reader would call mappings. A CTID
object repeating an earlier one in every field is counted in `duplicate_rows`;
one repeating its (control, technique) with any other field different refuses.
`mapping_objects_total` = `skipped_non_mappable` + `untranslated_rows` +
`duplicate_rows` + `rows`.

X2 LINES. Every "SP 800-53" line is placed or refused: a control under a
subcategory is composed; a whole FAMILY under a subcategory ("SP 800-53 Rev
5.1.1: PT") and a control under a CATEGORY row are disclosed in C1's header and
not composed (expanding either is an inference); anything else refuses. X2 rows
with no subcategory are counted by kind (function, category, other).

REVISION. X2 lists both "SP 800-53 Rev 5.1.1" and "Rev 5.2.0". Rev 5.1.1 is
used (Gene's ruling: the revision matching X1's control set). The difference
is recorded in C1's header: the controls only 5.2.0 lists, and whether X1 maps
any of them.

OUTPUT. `app/integration/data/x1_80053_attack.json` and `c1_csf_attack.json`,
deterministic (sorted, no timestamps), so a regeneration diff is reviewable and
`test_crosswalks.py` can re-derive them byte for byte.

USAGE (from apps/api, offline):  python scripts/derive_crosswalks.py

EXIT. 0 written; 2 refused (an input missing, a sha256 mismatch, or an input
SHIELD cannot place), with the cause on stderr.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.attack.catalog import SOURCE_VERSION as ATTACK_VERSION  # noqa: E402
from app.attack.catalog import all_codes as attack_codes  # noqa: E402
from app.csf.catalog import all_codes as csf_codes  # noqa: E402

DATA = API_ROOT / "app" / "integration" / "data"
REVOCATIONS = DATA / "attack_revocations_19.2.json"
X1_NAME = "ctid/nist_800_53-rev5_attack-16.1-enterprise.json"
X1_SHA256 = "355ae97d309c00eb2428e5af07754ff4ca16cfe63928194081d0e883aed929c8"
X1_COMMIT = "a85e55af3c9fa55359a98621745b9b039a088bec"
X2_NAME = "csf-2.0-reference-tool-export-2026-10-12.xlsx"
X2_SHA256 = "d83fbc04ea146e3ed4cacd3594351beab2359ae835669d607228528b43bb31a7"
REVISION = "5.1.1"
OTHER_REVISION = "5.2.0"

_SUBCATEGORY = re.compile(r"^([A-Z]{2}\.[A-Z]{2}-\d{2}):")
_REF = re.compile(r"^SP 800-53 Rev (\d+\.\d+\.\d+): ([A-Z]{2}-\d{2}(?:\(\d{2}\))?)$")
_FAMILY = re.compile(r"^SP 800-53 Rev (\d+\.\d+\.\d+): ([A-Z]{2})$")
_CATEGORY = re.compile(r"^[^(]*\(([A-Z]{2}\.[A-Z]{2})\):")


class Refused(Exception):
    """Maps to exit 2, with a named cause."""


def nist_dir(start: Path = API_ROOT) -> Path:
    """`reference-docs/nist` in a checkout, else the api container's mount, by
    the tests' own finder (one search, not two to keep in step)."""
    from tests._paths import ZT_SOURCES, find_zt_source

    found = find_zt_source(start, "nist")
    if found is None:
        raise Refused(f"reference-docs/nist not found in a checkout or at {ZT_SOURCES / 'nist'}")
    return found


def _read_pinned(path: Path, sha256: str) -> bytes:
    if not path.is_file():
        raise Refused(f"input missing: {path}")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256:
        raise Refused(f"{path.name}: sha256 {digest} does not equal the pinned {sha256}")
    return data


def _translator(revocations: dict, active: frozenset[str]):
    olds = [p["old"] for p in revocations["revoked_by"]]
    forked = sorted({old for old in olds if olds.count(old) > 1})
    if forked:
        raise Refused(f"the revocations file names more than one replacement for {forked}")
    revoked = {p["old"]: p["new"] for p in revocations["revoked_by"]}
    deprecated = set(revocations["deprecated"])

    def translate(code: str) -> tuple[str | None, str | None]:
        """(19.2 code, None) or (None, reason)."""
        seen = [code]
        while code not in active:
            if code in revoked:
                code = revoked[code]
                if code in seen:
                    return None, "revocation_cycle"
                seen.append(code)
                continue
            if code in deprecated:
                return None, "deprecated_in_19.2"
            return None, "absent_from_19.2"
        return code, None

    return translate


def derive_x1(x1_bytes: bytes, revocations: dict) -> dict:
    x1 = json.loads(x1_bytes)
    translate = _translator(revocations, attack_codes())
    first: dict[tuple[str, str, str], dict] = {}
    skipped_non_mappable = 0
    untranslated_rows = 0
    duplicate_rows = 0
    untranslated: dict[str, str] = {}
    for obj in x1["mapping_objects"]:
        if obj.get("mapping_type") != "mitigates":
            skipped_non_mappable += 1
            continue
        control, source = obj["capability_id"], obj["attack_object_id"]
        technique, reason = translate(source)
        if technique is None:
            untranslated[source] = reason or "unknown"
            untranslated_rows += 1
            continue
        key = (control, technique, source)
        if key in first:
            if first[key] != obj:
                raise Refused(f"X1 maps {control} to {source} twice, differently")
            duplicate_rows += 1
            continue
        first[key] = obj
    rows = set(first)
    return {
        "header": {
            "crosswalk": "X1",
            "source_url": "https://github.com/center-for-threat-informed-defense/mappings-explorer",
            "source_commit": X1_COMMIT,
            "source_path": "reference-docs/nist/" + X1_NAME,
            "source_sha256": X1_SHA256,
            "licence": "Apache-2.0",
            "mapping_framework": "NIST SP 800-53 rev5",
            "attack_version_source": x1["metadata"]["attack_version"],
            "attack_version_target": ATTACK_VERSION,
            "revocations_sha256": hashlib.sha256(REVOCATIONS.read_bytes()).hexdigest(),
            "mapping_objects_total": len(x1["mapping_objects"]),
            "skipped_non_mappable": skipped_non_mappable,
            "untranslated_rows": untranslated_rows,
            "duplicate_rows": duplicate_rows,
            "rows": len(rows),
            "control_technique_pairs": len({(c, t) for c, t, _s in rows}),
            "translated_rows": sum(1 for _c, t, s in rows if t != s),
            "untranslated": [{"id": i, "reason": r} for i, r in sorted(untranslated.items())],
            "script": "apps/api/scripts/derive_crosswalks.py",
        },
        "rows": [{"control": c, "technique": t, "attack_16_1": s} for c, t, s in sorted(rows)],
    }


@dataclass
class X2References:
    """X2's SP 800-53 lines, placed: {code: {revision: {control or family}}}."""

    refs: dict[str, dict[str, set[str]]]
    families: dict[str, dict[str, set[str]]]
    categories: dict[str, dict[str, set[str]]]
    third_party: dict[str, int]
    unplaced: dict[str, int]


def _sp_lines(cell: object) -> tuple[list[str], int]:
    """The "SP 800-53" lines of an Informative References cell, and how many
    other (third-party) lines it holds."""
    lines = [line.strip() for line in str(cell or "").splitlines() if line.strip()]
    sp = [line for line in lines if line.startswith("SP 800-53")]
    return sp, len(lines) - len(sp)


def _add(into: dict[str, dict[str, set[str]]], code: str, revision: str, value: str) -> None:
    into.setdefault(code, {}).setdefault(revision, set()).add(value)


def _x2_references(x2_path: Path) -> X2References:
    import openpyxl  # runtime dependency; imported here so `--help` stays cheap

    with warnings.catch_warnings():
        # The export carries no default style; openpyxl says so on every load.
        warnings.filterwarnings("ignore", message="Workbook contains no default style")
        sheet = openpyxl.load_workbook(x2_path, read_only=True)["CSF 2.0"]
    out = X2References(
        {},
        {},
        {},
        {"subcategory": 0, "category": 0, "function": 0},
        {"other": 0, "function": 0, "category": 0},
    )
    for row in sheet.iter_rows(values_only=True):
        cells = [*row, None, None, None, None, None][:5]
        sub = _SUBCATEGORY.match(cells[2]) if isinstance(cells[2], str) else None
        sp, other = _sp_lines(cells[4])
        if sub is not None:
            out.third_party["subcategory"] += other
            for line in sp:
                if ref := _REF.match(line):
                    _add(out.refs, sub.group(1), ref.group(1), ref.group(2))
                elif family := _FAMILY.match(line):
                    _add(out.families, sub.group(1), family.group(1), family.group(2))
                else:
                    raise Refused(f"unreadable SP 800-53 line {line!r} under {sub.group(1)}")
            continue
        category = _CATEGORY.match(cells[1]) if isinstance(cells[1], str) else None
        if category is not None and not cells[0]:
            out.unplaced["category"] += 1
            out.third_party["category"] += other
            for line in sp:
                ref = _REF.match(line)
                if ref is None:
                    raise Refused(f"unreadable SP 800-53 line {line!r} under {category.group(1)}")
                _add(out.categories, category.group(1), ref.group(1), ref.group(2))
            continue
        kind = "function" if cells[0] and not cells[1] else "other"
        out.unplaced[kind] += 1
        if kind == "function":
            out.third_party["function"] += other
        if sp:
            raise Refused(f"SP 800-53 line {sp[0]!r} on an X2 row with no subcategory or category")
    return out


def _only_other(found: dict[str, dict[str, set[str]]]) -> dict[str, list[str]]:
    """{code: [values]} named under the other revision and not under REVISION."""
    out = {}
    for code, revisions in sorted(found.items()):
        extra = revisions.get(OTHER_REVISION, set()) - revisions.get(REVISION, set())
        if extra:
            out[code] = sorted(extra)
    return out


def derive_c1(x2_path: Path, x1: dict) -> dict:
    x2 = _x2_references(x2_path)
    refs = x2.refs
    known = csf_codes()
    strangers = sorted((set(refs) | set(x2.families)) - known)
    if strangers:
        raise Refused(f"X2 names subcategories SHIELD's catalog lacks: {strangers}")
    categories = {code.rsplit("-", 1)[0] for code in known}
    strangers = sorted(set(x2.categories) - categories)
    if strangers:
        raise Refused(f"X2 names categories SHIELD's catalog lacks: {strangers}")
    by_control: dict[str, set[tuple[str, str]]] = {}
    for r in x1["rows"]:
        by_control.setdefault(r["control"], set()).add((r["technique"], r["attack_16_1"]))
    rows: set[tuple[str, str, str]] = set()
    no_x1: set[str] = set()
    only_other: set[str] = set()
    for code, revisions in refs.items():
        used = revisions.get(REVISION, set())
        only_other |= revisions.get(OTHER_REVISION, set()) - used
        for control in used:
            if control not in by_control:
                no_x1.add(control)
                continue
            rows.update((code, control, t) for t, _s in by_control[control])
    mapped = {s for s, _c, _t in rows}
    with_80053 = {c for c, r in refs.items() if r.get(REVISION)}
    with_80053 |= {c for c, r in x2.families.items() if r.get(REVISION)}
    unreached = {
        code: sorted(c for c in revisions.get(REVISION, set()) if c not in by_control)
        for code, revisions in refs.items()
    }
    return {
        "header": {
            "crosswalk": "C1",
            "x2_label": "NIST CSF 2.0 Reference Tool export, 2026-10-12",
            "x2_path": "reference-docs/nist/" + X2_NAME,
            "x2_sha256": X2_SHA256,
            "sp_800_53_revision": REVISION,
            "revision_difference": {
                "only_in_" + OTHER_REVISION: sorted(only_other),
                "x1_maps_any_of_them": any(c in by_control for c in only_other),
                f"families_only_in_{OTHER_REVISION}": _only_other(x2.families),
                f"category_references_only_in_{OTHER_REVISION}": _only_other(x2.categories),
                f"subcategories_only_in_{OTHER_REVISION}": sorted(
                    code
                    for code in set(refs) | set(x2.families)
                    if not refs.get(code, {}).get(REVISION)
                    and not x2.families.get(code, {}).get(REVISION)
                ),
            },
            "x1_sha256": hashlib.sha256(
                (json.dumps(x1, indent=2, ensure_ascii=False) + "\n").encode()
            ).hexdigest(),
            "third_party_lines_ignored": x2.third_party,
            "x2_rows_without_a_subcategory": x2.unplaced,
            "family_references_not_expanded": {
                code: sorted(r[REVISION])
                for code, r in sorted(x2.families.items())
                if r.get(REVISION)
            },
            "category_references_not_composed": {
                code: sorted(r[REVISION])
                for code, r in sorted(x2.categories.items())
                if r.get(REVISION)
            },
            "controls_without_techniques_by_subcategory": {
                code: controls for code, controls in sorted(unreached.items()) if controls
            },
            "subcategories_with_sp_800_53": len(with_80053),
            "subcategories_mapped": len(mapped),
            "subcategories_without_a_mapping": sorted(with_80053 - mapped),
            "controls_not_in_x1": sorted(no_x1),
            "rows": len(rows),
            "script": "apps/api/scripts/derive_crosswalks.py",
        },
        "rows": [{"subcategory": s, "control": c, "technique": t} for s, c, t in sorted(rows)],
    }


def derive(nist: Path) -> dict[str, bytes]:
    """{file name: exact bytes} for both outputs."""
    x1_bytes = _read_pinned(nist / X1_NAME, X1_SHA256)
    _read_pinned(nist / X2_NAME, X2_SHA256)
    if not REVOCATIONS.is_file():
        raise Refused(f"input missing: {REVOCATIONS}")
    x1 = derive_x1(x1_bytes, json.loads(REVOCATIONS.read_text(encoding="utf-8")))
    c1 = derive_c1(nist / X2_NAME, x1)
    return {
        "x1_80053_attack.json": (json.dumps(x1, indent=2, ensure_ascii=False) + "\n").encode(),
        "c1_csf_attack.json": (json.dumps(c1, indent=2, ensure_ascii=False) + "\n").encode(),
    }


def main(argv: list[str]) -> int:
    if argv:
        print(f"derive-crosswalks: REFUSED: takes no arguments, got {argv}", file=sys.stderr)
        return 2
    try:
        outputs = derive(nist_dir())
    except Refused as exc:
        print(f"derive-crosswalks: REFUSED: {exc}", file=sys.stderr)
        return 2
    for name, data in outputs.items():
        (DATA / name).write_bytes(data)
        header = json.loads(data)["header"]
        print(f"derive-crosswalks: wrote {name}: {header['rows']} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
