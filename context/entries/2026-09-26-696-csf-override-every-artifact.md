# 2026-09-26: a CSF playbook export gives each gap one priority (#696)

Branch `track2/csf-priority-override`, from `main` at `e851e59`.

## What changed

- **`/playbook/export` derives each gap's effective priority once** and hands
  the same rows to all five renderers. The stored `priority_override` wins
  where it is set; otherwise the gap keeps its computed priority. Before this,
  only the XLSX Action Plan read the override. The exec and full PDF/DOCX
  counted, listed and ranked the gap at its computed priority, and so did the
  XLSX Enterprise Profile sheet. The exec top 12 is one of the things that
  read the priority.
- **`_effective_priority` is the one rule**, and the gap-actions API uses it
  too. A row that is not a gap gets no priority, whatever override is stored
  against it. The upsert route accepts any catalogue code, so such a row can
  exist.
- **Review round 1:** the copy around the counts stays true for an override.
  The exec next steps count a P1 that a consultant set apart from the computed
  ones. Those are the only ones described as "Core-metric, high-impact,
  multi-system". The full playbook's methodology says a consultant may
  override a priority, and states how many were overridden, at zero too. The
  rows carry `priority_overridden`, which is set by the export route and never
  serialized.
- `csf/playbook_export.py` is edited in `_next_steps`, which #692 also edits.
  See the PR body for the pairwise result.

## Left as it is

- The Enterprise Profile endpoint, and the admin playbook panel's priority
  column that reads it, still show the computed priority. That is the default
  the gap-action editor shows beside the override.
- `upsert_gap_action` has no status guard. That was noted on #696 as a
  separate defect.
