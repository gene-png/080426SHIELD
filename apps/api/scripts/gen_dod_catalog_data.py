"""Generate `app/zt/_dod_catalog_data.py` from the committed DoD extraction (#839).

The DoD catalog's capabilities and activities are the extraction's, generated
like ATT&CK's `_catalog_data.py` from STIX, and `test_zt_dod_catalog_source.py`
holds the catalog to the extraction. Re-run after re-extracting:

    python apps/api/scripts/gen_dod_catalog_data.py

Exit 2 when there is no checkout or no extraction to read.
"""

from __future__ import annotations

import json
import pprint
import sys
from pathlib import Path

#: DoD pillar number -> the catalog's pillar code, unchanged since v1.
PILLAR_CODES = {1: "USR", 2: "DEV", 3: "APP", 4: "DAT", 5: "NET", 6: "AUT", 7: "VIS"}

HEADER = '''# ruff: noqa: E501
"""DoD Zero Trust capabilities and activities, GENERATED: do not edit.

From `reference-docs/dod/dod_zt_2025_rows.json` (DoD CIO, 2025, 25-T-1465,
sha256 {sha}) by `apps/api/scripts/gen_dod_catalog_data.py`.
Edit the extraction and regenerate; never edit this file.
"""

# fmt: off
'''


def described(a: dict) -> str:
    """An activity's description, plus its outcomes and its End State where the
    2025 edition gives one (#839 comment 5983310584)."""
    parts = [a["description"]]
    if a["outcomes"]:
        parts.append("Outcomes: " + a["outcomes"])
    if a["end_state"]:
        parts.append("End state: " + a["end_state"])
    return " ".join(parts)


def render(src: dict) -> str:
    caps = tuple(
        (
            PILLAR_CODES[c["pillar_number"]],
            c["pillar"],
            c["id"],
            f"DOD.{PILLAR_CODES[c['pillar_number']]}.{int(c['id'].split('.')[1]):02d}",
            c["name"],
            c["description"],
        )
        for c in src["capabilities"]
    )
    acts = tuple((a["id"], a["name"], a["level"], described(a)) for a in src["activities"])
    return (
        HEADER.format(sha=src["source"]["sha256"])
        + "\n#: (pillar code, pillar name, DoD number, catalog code, name, description)\n"
        + "DOD_CAPABILITY_ROWS: tuple[tuple[str, str, str, str, str, str], ...] = "
        + pprint.pformat(caps, width=100)
        + "\n\n#: (DoD activity id, name, level, description with outcomes and End State)\n"
        + "DOD_ACTIVITY_ROWS: tuple[tuple[str, str, str, str], ...] = "
        + pprint.pformat(acts, width=100)
        + "\n# fmt: on\n"
    )


def main() -> int:
    here = Path(__file__).resolve().parent
    repo = next((d for d in (here, *here.parents) if (d / "reference-docs").is_dir()), None)
    if repo is None:
        print("NO CHECKOUT: no reference-docs/ at or above this script", file=sys.stderr)
        return 2
    src_path = repo / "reference-docs" / "dod" / "dod_zt_2025_rows.json"
    try:
        src = json.loads(src_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"COULD NOT READ {src_path}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    dest = repo / "apps" / "api" / "app" / "zt" / "_dod_catalog_data.py"
    dest.write_bytes(render(src).encode("utf-8"))
    print(
        f"wrote {dest} ({len(src['capabilities'])} capabilities, {len(src['activities'])} activities)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
