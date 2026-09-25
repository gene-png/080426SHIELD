# 2026-09-25: an ATT&CK parent's status is computed from its sub-techniques (#554, D-094)

Branch `track2/attack-computed-parents`, from `main` at `2028f38`.

## What changed

- **`app/attack/parents.py`**: the rule (`computed_parent_status`), the set of
  parents it applies to (`PARENT_CHILDREN`, from the catalog: 95 of 193
  parents have sub-techniques), and `recompute_parents` for the write paths.
- **PATCH** refuses a computed parent's status or reason (typed 422
  `parent_status_computed`) and recomputes a child's parent in the same
  transaction.
- **Run AI** refuses a parent's suggestion whole and recomputes every parent
  before its diff. **Approve** recomputes every parent before freezing. All
  three are audited.
- **The demo seed** recomputes through the same function.
- **The workspace** disables a computed parent's status buttons and says it
  follows its N sub-techniques.

## Not in this slice

- The release gate reading a computed parent's children (c3).
- Existing APPROVED or RELEASED assessments are not rewritten; only a new
  approval recomputes.
