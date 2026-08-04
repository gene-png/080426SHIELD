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
