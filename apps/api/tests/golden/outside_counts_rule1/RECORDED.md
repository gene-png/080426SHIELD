# Recorded once, never regenerated

These files are the DOCX, PDF and XLSX that `main` rendered for a rule-1 (approved
before #620) ATT&CK assessment **before #621**. They pin option (a): #621's
counts and columns appear only under D-094's rules, and an assessment approved
before #620 renders what was delivered.

- **Recorded from:** `main` at `22c47a4` (#657), which contains #620 and not #621.
- **Recorded on:** 2026-09-26, in a `--rm` `shield-v2-api` container mounting a
  detached worktree at that commit.
- **How:** `record()` in `tests/unit/test_attack_outside_counts_follow_the_rule_set.py`,
  copied into that worktree and called with this directory. `world(1)` builds the
  world. It uses only the four legacy statuses, one pending claim and unscored
  techniques, which is what a rule-1 assessment can hold.

Do not regenerate these to make a test pass. A difference is the defect.

## Amendment, 2026-10-02: the #646 AI-source stamp (Phase 2 Batch F)

The coordinator's verdict on Batch F, Q1 (b): every deliverable states which
mode drafted its AI suggestions, an ADDED disclosure. These files were
re-rendered from the same `world(1)` by the current code and checked against
the recorded ones before replacing them. The world's context is built without
a lookup, so it states "not recorded":

- `docx.json`: one paragraph added, the stamp, directly under the title and
  client name. Every other entry is identical and in the same order.
- `pdf.json`: the same sentence inserted under the title on page 1. With it
  removed, the words are identical.
- `xlsx.json`: the four recorded sheets are identical, and a fifth, "AI
  source", is added last.

## Amendment, 2026-10-02: the #554 R1 Partial reason

The coordinator's ruling on #554 R1, option (a), approved by Gene's advisor:
the client sees WHY a technique is Partial on assessments approved before #620
too. It is an ADDED disclosure. In this world every Partial carries no reason,
so it reads "Reason not recorded". These files were re-rendered from the same
`world(1)` by the current code and checked against the files above before
replacing them, by a throwaway script that asserted each difference was an
insertion and nothing else:

- `docx.json`: three entries inserted after the coverage summary: the heading
  "Partial coverage, by reason", the table header "Reason | What it means |
  Techniques", and one row, "Reason not recorded | ... | 140". 140 is the
  world's Partial figure. Every other entry is identical and in the same order.
- `pdf.json`: the same heading, header and row are inserted on page 1. With
  those words removed, the words are identical.
- `xlsx.json`: the Coverage sheet gains a "Why partial" column after "Pending
  review". With that column removed from every row, the sheet is identical.
  The Heatmap Summary gains one legend row, "Why partial". With it removed,
  the sheet is identical. The other sheets are unchanged.
