"""Zero Trust assessment module (Phase 5).

Two frameworks live here as code-only reference data:

  - CISA ZTMM 2.0 (Apr 2023 final): 5 + 3 pillars, ~37 capabilities,
    Traditional / Initial / Advanced / Optimal maturity stages.
  - DoD Zero Trust Reference Architecture (Nov 2022): 7 pillars, 152
    activities total; v1 baseline encodes a representative ~50.

Catalogs are immutable code; the engagement's *answers* land in
`zt_answers` keyed by (assessment_id, capability_code).
"""
