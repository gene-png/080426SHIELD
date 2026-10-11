"""Count the DoD extraction's capabilities, activities and levels (#839, D-109).

Reads `reference-docs/dod/dod_zt_2025_rows.json` (or the path given) and prints:

* the number of capabilities and activities, and activities per level;
* the capabilities with no Advanced activity (their target is capped at 2);
* the capabilities with no Target activity (disclosed only).

It is the command D-109's figures cite, so they can be re-derived rather than
recalled. It counts; it decides nothing.

    python apps/api/scripts/count_dod_levels.py [path/to/dod_zt_2025_rows.json]

Exit 0 after printing. Exit 2 when the file cannot be read or does not have the
shape the extraction writes, so "could not look" never prints a count.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[3] / "reference-docs" / "dod" / "dod_zt_2025_rows.json"


def count(data: dict) -> dict:
    caps = [c["id"] for c in data["capabilities"]]
    levels_by_cap: dict[str, set[str]] = {c: set() for c in caps}
    per_level: dict[str, int] = {}
    for act in data["activities"]:
        cap = act["id"].rsplit(".", 1)[0]
        if cap not in levels_by_cap:
            raise ValueError(f"activity {act['id']} names no capability in the extraction")
        levels_by_cap[cap].add(act["level"])
        per_level[act["level"]] = per_level.get(act["level"], 0) + 1
    return {
        "capabilities": len(caps),
        "activities": len(data["activities"]),
        "per_level": per_level,
        "no_advanced": [c for c in caps if "advanced" not in levels_by_cap[c]],
        "no_target": [c for c in caps if "target" not in levels_by_cap[c]],
    }


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT
    try:
        result = count(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"count-dod-levels: could not read {path}: {exc!r}", file=sys.stderr)
        return 2
    print(f"count-dod-levels: {path}")
    print(f"  capabilities {result['capabilities']}, activities {result['activities']}")
    print(f"  activities per level {result['per_level']}")
    print(
        f"  no Advanced activity ({len(result['no_advanced'])}): {', '.join(result['no_advanced'])}"
    )
    print(f"  no Target activity ({len(result['no_target'])}): {', '.join(result['no_target'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
