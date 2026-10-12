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
CONTAINER_NIST = Path("/zt-sources/nist")

_SUBCATEGORY = re.compile(r"^([A-Z]{2}\.[A-Z]{2}-\d{2}):")
_REF = re.compile(r"^SP 800-53 Rev (\d+\.\d+\.\d+): ([A-Z]{2}-\d{2}(?:\(\d{2}\))?)$")


class Refused(Exception):
    """Maps to exit 2, with a named cause."""


def nist_dir(start: Path = API_ROOT) -> Path:
    """`reference-docs/nist` in a checkout, else the api container's mount."""
    for candidate in [start, *start.parents]:
        directory = candidate / "reference-docs" / "nist"
        if directory.is_dir():
            return directory
    if CONTAINER_NIST.is_dir():
        return CONTAINER_NIST
    raise Refused("reference-docs/nist not found in a checkout or at /zt-sources/nist")


def _read_pinned(path: Path, sha256: str) -> bytes:
    if not path.is_file():
        raise Refused(f"input missing: {path}")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256:
        raise Refused(f"{path.name}: sha256 {digest} does not equal the pinned {sha256}")
    return data


def _translator(revocations: dict, active: frozenset[str]):
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
    rows: set[tuple[str, str, str]] = set()
    skipped_non_mappable = 0
    untranslated: dict[str, str] = {}
    for obj in x1["mapping_objects"]:
        if obj.get("mapping_type") != "mitigates":
            skipped_non_mappable += 1
            continue
        control, source = obj["capability_id"], obj["attack_object_id"]
        technique, reason = translate(source)
        if technique is None:
            untranslated[source] = reason or "unknown"
            continue
        rows.add((control, technique, source))
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
            "rows": len(rows),
            "translated_rows": sum(1 for _c, t, s in rows if t != s),
            "untranslated": [{"id": i, "reason": r} for i, r in sorted(untranslated.items())],
            "script": "apps/api/scripts/derive_crosswalks.py",
        },
        "rows": [{"control": c, "technique": t, "attack_16_1": s} for c, t, s in sorted(rows)],
    }


def _x2_references(x2_path: Path) -> tuple[dict[str, dict[str, set[str]]], int, int]:
    """{subcategory: {revision: {controls}}}, third-party lines, other rows."""
    import openpyxl  # runtime dependency; imported here so `--help` stays cheap

    with warnings.catch_warnings():
        # The export carries no default style; openpyxl says so on every load.
        warnings.filterwarnings("ignore", message="Workbook contains no default style")
        sheet = openpyxl.load_workbook(x2_path, read_only=True)["CSF 2.0"]
    refs: dict[str, dict[str, set[str]]] = {}
    third_party = 0
    unplaced = 0
    for row in sheet.iter_rows(values_only=True):
        cell = row[2] if len(row) > 2 else None
        match = _SUBCATEGORY.match(cell) if isinstance(cell, str) else None
        if match is None:
            unplaced += 1
            continue
        code = match.group(1)
        for line in str(row[4] or "").splitlines():
            ref = _REF.match(line.strip())
            if ref is None:
                third_party += 1
                continue
            refs.setdefault(code, {}).setdefault(ref.group(1), set()).add(ref.group(2))
    return refs, third_party, unplaced


def derive_c1(x2_path: Path, x1: dict) -> dict:
    refs, third_party, unplaced = _x2_references(x2_path)
    known = csf_codes()
    strangers = sorted(set(refs) - known)
    if strangers:
        raise Refused(f"X2 names subcategories SHIELD's catalog lacks: {strangers}")
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
            },
            "x1_sha256": hashlib.sha256(
                (json.dumps(x1, indent=2, ensure_ascii=False) + "\n").encode()
            ).hexdigest(),
            "third_party_lines_ignored": third_party,
            "x2_rows_without_a_subcategory": unplaced,
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
