# MITRE CTID Mappings Explorer: NIST SP 800-53 rev5 to ATT&CK 16.1 (crosswalk X1)

- **File:** `nist_800_53-rev5_attack-16.1-enterprise.json`, copied unmodified.
- **sha256:** `355ae97d309c00eb2428e5af07754ff4ca16cfe63928194081d0e883aed929c8`
- **Source:** `https://github.com/center-for-threat-informed-defense/mappings-explorer`, commit `a85e55af3c9fa55359a98621745b9b039a088bec` (2026-10-04), path `mappings/nist_800_53/attack-16.1/nist_800_53-rev5/enterprise/`.
- **Licence:** Apache-2.0 (`LICENSE.txt` here, `NOTICE` for attribution).
- **Its own metadata:** `attack_version` "16.1", `mapping_framework_version` "rev5", `last_update` "04/16/2025", mapping type `mitigates`.
- **Use:** derived offline by `apps/api/scripts/derive_crosswalks.py` into `apps/api/app/integration/data/` (crosswalks X1 and C1, track D design note rev 5 section 12, #736). Technique IDs are translated from ATT&CK 16.1 to SHIELD's 19.2 with `apps/api/app/integration/data/attack_revocations_19.2.json`.
- **Why under `nist/`:** `docker-compose.yml` already mounts `reference-docs/nist` read-only into the api container (`/zt-sources/nist`), so the derivation's determinism test runs there without a compose change.
