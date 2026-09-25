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

## Round 1 (review of 672738e)

- **Pending review is derived over the whole assessment.** A computed parent
  is pending if and only if it claims support and one of its children is
  pending. Its own citations are never read. The route sets each row's flag
  from `pending_codes`, so the heatmap, the dashboard and the badge agree.
- **Locks.** PATCH refuses `locked` on a computed parent. A parent locked
  before this rule is unlocked when recomputed and audited as
  `parents_unlocked`. Run AI takes unlocked parents out of its locked set, so
  its diff shows the recompute.
- **The workspace refetches** the assessment and heatmap after a
  sub-technique's status or reason changes, so the parent on screen is not
  stale.
- **The panel shows a computed parent's reason and lock, and offers
  neither.** The API refuses both. #603's reason select arrived with the
  `main` merge (34f0e33) and was live on a parent, and my round 1 had
  refused the lock on the API while leaving its checkbox live.
- **CI was red at 672738e** (13 tests in `test_attack_pending_persistence.py`,
  picking T1001 as `codes[0]`). The earlier sweep missed that spelling. They,
  and one exporter test picking T1003, now use standalone techniques.
- **Populations** (D-094): DRAFTs correct at their next write or at approve.
  APPROVED-never-released assessments are never recomputed. The shared dev DB
  had 0 of them on 2026-09-25. Whether any deployment needs a one-time pass is
  the owner's call.
