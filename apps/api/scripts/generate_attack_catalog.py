"""Generate the ATT&CK catalog from MITRE's published STIX (#556).

WHY THIS EXISTS. The catalog used to be hand-encoded and labelled "v15". It
matched no released version: 17 real techniques missing (all of T1553 among
them), T1558 and T1649 carrying each other's names, four sub-technique IDs
that do not exist in ATT&CK, v16 additions grafted onto a v15 base, and
editorial suffixes such as "(also DE)" in client-facing names. A hand list that
must be kept in sync with MITRE's data drifts; a list DERIVED from that data
cannot, and the version it records is true by construction.

WHAT IT DOES. Reads one full `enterprise-attack-<version>.json` from
mitre-attack/attack-stix-data, refuses unless its collection object names the
version you asked for, and writes two files:

  * `app/attack/stix/enterprise-attack-<version>.subset.json.gz`: MITRE's own
    objects of four types (attack-pattern, x-mitre-tactic, x-mitre-matrix,
    x-mitre-collection), each byte-for-byte as published and only SELECTED by
    type, so any one can be checked against upstream by its STIX id. The tests
    parse this with their own code, never with this script's.
  * `app/attack/_catalog_data.py`: the tactics in matrix order and every
    active technique (revoked and deprecated excluded), with the source URL,
    version and the full file's sha256.

USAGE (from apps/api):

    curl -sSLo /tmp/ea.json https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack-19.2.json
    python scripts/generate_attack_catalog.py --stix /tmp/ea.json --version 19.2

EXIT CODES: 0 written; 2 could not look -- unreadable file, a collection
version that is not the one asked for, a matrix or tactic missing, or an
unknown argument. There is no exit 1: this is a generator, not a gate. A crash
exits with Python's own traceback.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

URL_TEMPLATE = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/"
    "enterprise-attack/enterprise-attack-{version}.json"
)
KEEP_TYPES = ("attack-pattern", "x-mitre-tactic", "x-mitre-matrix", "x-mitre-collection")
API_ROOT = Path(__file__).resolve().parents[1]
DATA_MODULE = API_ROOT / "app" / "attack" / "_catalog_data.py"
SUBSET_DIR = API_ROOT / "app" / "attack" / "stix"


class CouldNotLook(Exception):
    """Maps to exit 2."""


def _mitre_id(obj: dict) -> str | None:
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack":
            return ref.get("external_id")
    return None


def _active(obj: dict) -> bool:
    return not obj.get("revoked") and not obj.get("x_mitre_deprecated")


def _first_sentence(text: str) -> str:
    """The tactic description's first sentence; MITRE's text, not a paraphrase."""
    text = " ".join(text.split())
    end = text.find(". ")
    return text if end == -1 else text[: end + 1]


def build(bundle: dict, version: str) -> tuple[list[tuple], list[tuple]]:
    objs = bundle.get("objects", [])
    colls = [o for o in objs if o.get("type") == "x-mitre-collection"]
    found = [c.get("x_mitre_version") for c in colls]
    if found != [version]:
        raise CouldNotLook(f"collection version is {found!r}, not [{version!r}]")
    matrices = [o for o in objs if o.get("type") == "x-mitre-matrix" and _active(o)]
    if len(matrices) != 1:
        raise CouldNotLook(f"expected one active matrix, found {len(matrices)}")
    by_stix = {o["id"]: o for o in objs if o.get("type") == "x-mitre-tactic"}
    tactics: list[tuple] = []
    for ref in matrices[0]["tactic_refs"]:
        t = by_stix.get(ref)
        if t is None or not _active(t):
            raise CouldNotLook(f"matrix names tactic {ref} that is missing or inactive")
        tactics.append(
            (_mitre_id(t), t["x_mitre_shortname"], t["name"], _first_sentence(t["description"]))
        )
    order = {short: i for i, (_, short, _, _) in enumerate(tactics)}
    tid_by_short = {short: tid for tid, short, _, _ in tactics}
    techniques: list[tuple] = []
    for o in objs:
        if o.get("type") != "attack-pattern" or not _active(o):
            continue
        code = _mitre_id(o)
        if code is None:
            raise CouldNotLook(f"attack-pattern {o['id']} has no mitre-attack external id")
        shorts = sorted(
            {
                p["phase_name"]
                for p in o.get("kill_chain_phases", [])
                if p.get("kill_chain_name") == "mitre-attack"
            },
            key=lambda s: order.get(s, len(order)),
        )
        unknown = [s for s in shorts if s not in tid_by_short]
        if unknown:
            raise CouldNotLook(f"{code} names tactics not in the matrix: {unknown}")
        is_sub = bool(o.get("x_mitre_is_subtechnique"))
        parent = code.split(".")[0] if is_sub else None
        techniques.append((code, o["name"], tuple(tid_by_short[s] for s in shorts), parent))
    techniques.sort(key=lambda t: t[0])
    codes = {t[0] for t in techniques}
    orphans = [t[0] for t in techniques if t[3] is not None and t[3] not in codes]
    if orphans:
        raise CouldNotLook(f"sub-techniques whose parent is not active: {orphans}")
    return tactics, techniques


def subset_bytes(bundle: dict) -> bytes:
    kept = [o for o in bundle["objects"] if o.get("type") in KEEP_TYPES]
    body = {"type": "bundle", "id": bundle.get("id"), "objects": kept}
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return gzip.compress(raw.encode("utf-8"), compresslevel=9, mtime=0)


def render(version: str, url: str, sha256: str, subset_name: str, tactics, techniques) -> str:
    lines = [
        '"""GENERATED by scripts/generate_attack_catalog.py -- do not edit by hand.',
        "",
        "Regenerate from MITRE's published STIX; see that script's docstring (#556).",
        '"""',
        "",
        "# ruff: noqa: E501",
        "# fmt: off",
        "SOURCE = {",
        '    "collection": "Enterprise ATT&CK",',
        f'    "version": {version!r},',
        f'    "url": {url!r},',
        f'    "sha256": {sha256!r},',
        f'    "subset": {subset_name!r},',
        "}",
        "",
        "# (id, shortname, name, description) in MITRE's matrix order.",
        "TACTICS_DATA = (",
    ]
    lines += [f"    {t!r}," for t in tactics]
    lines += [
        ")",
        "",
        "# (id, name, tactic ids, parent id or None), sorted by id.",
        "TECHNIQUES_DATA = (",
    ]
    lines += [f"    {t!r}," for t in techniques]
    lines += [")", "# fmt: on", ""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = dict(zip(argv[1::2], argv[2::2], strict=False))
    if set(args) - {"--stix", "--version"} or "--stix" not in args or "--version" not in args:
        print("generate-attack-catalog: could not look -- need --stix <file> --version <x.y>")
        return 2
    version = args["--version"]
    try:
        raw = Path(args["--stix"]).read_bytes()
        bundle = json.loads(raw)
        tactics, techniques = build(bundle, version)
    except (OSError, ValueError, KeyError, CouldNotLook) as exc:
        print(f"generate-attack-catalog: could not look -- {type(exc).__name__}: {exc}")
        return 2
    sha = hashlib.sha256(raw).hexdigest()
    subset_name = f"enterprise-attack-{version}.subset.json.gz"
    SUBSET_DIR.mkdir(parents=True, exist_ok=True)
    (SUBSET_DIR / subset_name).write_bytes(subset_bytes(bundle))
    DATA_MODULE.write_text(
        render(
            version, URL_TEMPLATE.format(version=version), sha, subset_name, tactics, techniques
        ),
        encoding="utf-8",
        newline="\n",
    )
    parents = sum(1 for t in techniques if t[3] is None)
    print(
        f"generate-attack-catalog: wrote v{version} -- {len(tactics)} tactics, {parents} "
        f"techniques, {len(techniques) - parents} sub-techniques; source sha256 {sha[:16]}"
    )
    return 0


if __name__ == "__main__":
    # A GENERATOR, not a gate: no CI step runs it and nothing reads its exit code
    # as a verdict, so it carries no crash handler (check_gate_fixtures treats a
    # script with one as a gate). A crash prints a traceback and exits non-zero.
    raise SystemExit(main(sys.argv))
