"""MITRE ATT&CK Enterprise coverage module (Phase 5 stage 5).

The full ATT&CK Enterprise matrix lives in `app.attack.catalog` as
immutable code data: 14 tactics, ~196 techniques, ~411 sub-techniques.
Per D-007 (Decisions log) we encode the complete matrix rather than a
curated subset.

The coverage model uses a different shape from the maturity-tier
services (Tech Debt / CSF / Zero Trust): each technique gets a single
coverage *status* (covered / partial / gap / not_applicable) rather
than a 1-4 score. Heatmap rendering uses the tactic-to-technique
matrix to surface defensive coverage at a glance.
"""
