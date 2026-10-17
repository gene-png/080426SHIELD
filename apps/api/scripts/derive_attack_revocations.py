"""Derive ATT&CK 19.2's revocation pairs and deprecated IDs (N10, for #1063).

WHY. Crosswalk X1 (MITRE CTID, SP 800-53 rev5 to ATT&CK 16.1) names techniques
by their 16.1 IDs; SHIELD's catalog is 19.2. Translating needs MITRE's
`revoked-by` relationships, which the vendored subset
(`app/attack/stix/enterprise-attack-19.2.subset.json.gz`) does not keep. This
script reads them from the FULL 19.2 bundle once, and writes a small committed
file. Nothing at runtime or in CI fetches from the network.

WHAT IT DOES. Downloads the bundle from the URL pinned in
`app.attack._catalog_data.SOURCE`, refuses unless its sha256 equals the pinned
SOURCE sha256 (read by import, never retyped), and writes
`app/integration/data/attack_revocations_19.2.json`:

  header      source URL, sha256, attack-stix-data commit (given), generated date
  revoked_by  [{"old": "T1086", "new": "T1059.001"}, ...], sorted by old, new;
              each old ID at most once (two replacements for one ID refuse)
  deprecated  ["T1064", ...], sorted

Only attack-pattern objects (techniques) are read.

USAGE (from apps/api, network required):

    python scripts/derive_attack_revocations.py --commit <attack-stix-data sha>

EXIT. 0 written; 2 refused (sha256 mismatch, a fetch failure, or a bad
argument), with the cause on stderr. There is no exit 1: this is a generator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.attack._catalog_data import SOURCE  # noqa: E402

OUT = API_ROOT / "app" / "integration" / "data" / "attack_revocations_19.2.json"


class Refused(Exception):
    """Maps to exit 2, with a named cause."""


def _mitre_id(obj: dict) -> str | None:
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack":
            return ref.get("external_id")
    return None


def _fetch(url: str) -> bytes:
    if not url.startswith("https://raw.githubusercontent.com/mitre-attack/"):
        raise Refused(f"refusing a URL outside MITRE's repository: {url}")
    try:
        with urllib.request.urlopen(url, timeout=300) as response:  # noqa: S310 - pinned https
            return response.read()
    except OSError as exc:
        raise Refused(f"could not fetch {url}: {exc}") from exc


def derive(bundle: bytes, *, commit: str, generated: str) -> dict:
    digest = hashlib.sha256(bundle).hexdigest()
    if digest != SOURCE["sha256"]:
        raise Refused(f"sha256 {digest} does not equal the pinned SOURCE sha256 {SOURCE['sha256']}")
    objects = json.loads(bundle)["objects"]
    techniques = {o["id"]: o for o in objects if o.get("type") == "attack-pattern"}
    pairs: set[tuple[str, str]] = set()
    for rel in objects:
        if rel.get("type") != "relationship" or rel.get("relationship_type") != "revoked-by":
            continue
        old, new = techniques.get(rel["source_ref"]), techniques.get(rel["target_ref"])
        if old is None or new is None:
            continue  # a revoked mitigation or group, not a technique
        old_id, new_id = _mitre_id(old), _mitre_id(new)
        if old_id is None or new_id is None:
            raise Refused(f"revoked-by {rel['id']} joins a technique with no ATT&CK ID")
        pairs.add((old_id, new_id))
    olds = [old for old, _new in pairs]
    forked = sorted({old for old in olds if olds.count(old) > 1})
    if forked:
        # One ID revoked into two techniques has no single translation.
        raise Refused(f"revoked-by names more than one replacement for {forked}")
    deprecated = sorted(
        i
        for o in techniques.values()
        if o.get("x_mitre_deprecated") and not o.get("revoked")
        for i in [_mitre_id(o)]
        if i is not None
    )
    return {
        "header": {
            "source_url": SOURCE["url"],
            "source_sha256": digest,
            "attack_version": SOURCE["version"],
            "attack_stix_data_commit": commit,
            "generated": generated,
            "script": "apps/api/scripts/derive_attack_revocations.py",
        },
        "revoked_by": [{"old": o, "new": n} for o, n in sorted(pairs)],
        "deprecated": deprecated,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--commit", required=True, help="attack-stix-data commit sha")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
            raise Refused(f"--commit must be a 40-character git sha, not {args.commit!r}")
        out = derive(
            _fetch(SOURCE["url"]),
            commit=args.commit,
            generated=datetime.now(UTC).strftime("%Y-%m-%d"),
        )
    except Refused as exc:
        print(f"derive-attack-revocations: REFUSED: {exc}", file=sys.stderr)
        return 2
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"derive-attack-revocations: wrote {OUT.name}: {len(out['revoked_by'])} revoked-by "
        f"pairs, {len(out['deprecated'])} deprecated IDs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
