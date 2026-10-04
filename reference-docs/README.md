# reference-docs

Locked SHIELD v2 reference documents: the Master Spec, AI build prompt, Round
6 design contract, questionnaires, mockup, and the CSF working-profile /
interview workbooks. Filenames were normalized on import (DECISIONS D-013).
Treat everything here as read-only input — corrections and deviations are
recorded in `DECISIONS.md`, never by editing these files.

## Missing on purpose: the v2 Developer Work Order (Parts A–F)

The Parts A–F work order that produced the `v3.0.0` merge (PR #1) was **not
supplied as a document** and is not in this directory. Its decisions live in
`DECISIONS.md` (D-015 multi-tenant, D-021 Part F harden-and-ship, D-023
reviewer/release-flow supersession) and in code comments at the points they
bind. If David supplies the original work-order document later, commit it
here and update this note.

## `cisa/`: CISA ZTMM 2.0, the source of record for the ZT catalog (#838)

`cisa/zero_trust_maturity_model_v2_508.pdf` is CISA's *Zero Trust Maturity
Model*, Version 2.0, April 2023, downloaded from cisa.gov on 2026-10-04
(sha256 `4a95fdff55a64e2468b69af075b7f208176b88c751af92aefc3b7dacad26fdb4`).
`cisa/cisa_ztmm_v2_rows.json` is its extraction (Tables 2-6: 37 rows, each
pillar's Optimal text and definition) by `apps/api/scripts/extract_zt_sources.py`,
which also re-derives it from the PDF for review. The catalog will be tested
against this extraction (#838 PR 2), never against its own constants.

## `dod/`: DoD's Zero Trust documents, the source for the DoD catalog (#839)

The 2025 DoD CIO *Zero Trust Execution Roadmap (COAs 1-3)*, 25-T-1465, and the
2022 *DoD ZT Capability Execution Roadmap*, with their hashes, dates and source
URLs in `dod/README.md`. Pinning (#839 comment 5983310584): the catalog takes
the 2025 edition's capabilities and activities, with each Advanced level
cross-checked against the 2022 Roadmap. No extraction yet; that is the DoD
catalog PR.

## Known spec discrepancies

- **"108 subcategories" vs 106 implemented.** `SHIELDv2_Master_Spec.txt`
  repeatedly says the CSF 2.0 subcategory model has **108** leaf items (e.g.
  the tiered-interview and working-profile sections). NIST CSF 2.0 **Final**
  defines **106** subcategories, and that is what ships:
  `apps/api/app/csf/catalog.py` `SUBCATEGORIES` has 106 entries carrying the
  NIST Final verbatim text (the source of record for interview prompts — see
  SMOKE_TEST §3). The spec's 108 appears to count a pre-final draft. The
  implementation follows NIST Final, not the spec's number.
- **Single-tenant (spec §2) is superseded** by the multi-tenant architecture
  (DECISIONS D-015).
- **Celery workers (spec §2) were removed** — AI jobs run synchronously in
  the API (DECISIONS D-021).
- On UI conflicts, `Shield_UX_Round6_Design_Contract.txt` governs over the
  Master Spec (per the README pointer).
