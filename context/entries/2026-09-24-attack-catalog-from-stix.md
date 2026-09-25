# 2026-09-24: the ATT&CK catalog is generated from MITRE's STIX, at v19.2 (#556, D-091)

Branch `track2/catalog-from-stix`, base `f17cc5a`.

## Why

The hand-encoded "v15" catalog matched no ATT&CK release. It was missing 17
real techniques, swapped the names of T1558 and T1649, scored four
sub-technique IDs that do not exist, and put editorial suffixes such as
"(also DE)" into client deliverables. Every ATT&CK coverage number so far was
computed over that denominator. #556 is tier-1.

## What changed

- **`scripts/generate_attack_catalog.py`** reads one MITRE STIX file. It
  refuses a file whose collection version is not the one requested (checked:
  an 18.1 file offered as 19.2 exits 2). It writes:
  - `app/attack/_catalog_data.py`, recording the version, URL and sha256;
  - a type-selected subset of MITRE's objects (value-equal, not byte-equal), at
    `app/attack/stix/enterprise-attack-19.2.subset.json.gz` (1.4 MB).
- **`app/attack/catalog.py`** is now a loader over the generated data. The
  public API is unchanged, plus `SOURCE` and `SOURCE_VERSION`.
- **v19.2:** 15 tactics, 222 techniques, 475 sub-techniques.
  - TA0005 is now Stealth; TA0112 Defense Impairment is new.
  - T1562 Impair Defenses and its sub-techniques are revoked in v19.2, and
    leave the catalog.
- **Tests.** `test_attack_catalog_matches_stix.py` parses the subset with its
  own code, so a catalog that disagrees with MITRE fails it rather than
  agreeing by construction. The two `len(TACTICS) == 14` pins now derive from
  the release the catalog claims.

## A stale assessment is refused, not silently computed

The coverage readers used to keep only rows whose code was in the catalog. After
a catalog change that would have turned every old assessment into a percentage
over a mixed, undisclosed set.

- **Migration 0052** adds `attack_assessments.catalog_version`. It is stamped at
  creation and NULL for every existing row.
- **Every reader that computes, changes or publishes coverage refuses** a stale
  assessment with a typed 409 `attack_catalog_mismatch`: PATCH,
  confirm-citations, Run-AI, heatmap, approve, finalize, first release, the client
  dashboard (client wording) and risk synthesis. The value-summary card reports
  the kind unresolved. The assessment GET and the discard count stay unguarded
  on purpose, because neither computes a coverage number.
- **The workspace** shows the refusal's own message.
- **Red-on-revert:** removing each guard call turns a named test red.
- **Gap:** an approved or released assessment has no rescore control (#558).

## The path, and what it rests on

The owner's rule: all test data → v19.2, discard and rescore, one move. The
count on 2026-09-24 was 0 real client assessments anywhere reachable. That
rests on nobody having run a real engagement on an unreached stack. The
migration plan is on #556, with the name-not-ID rule.

## Not in this PR

- Existing coverage rows in any database. The plan says discard and rescore;
  no data migration runs here.
- The status vocabulary (#554).
