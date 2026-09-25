# 2026-09-25: the ATT&CK AI draft gives reason codes (#554 slice 2, D-093)

Branch `track2/attack-ai-reason-codes`, from `main` at `ef94f4f`.

## What changed

- **The `mitre_map` prompt** asks for a `reason_code`: one of the seven
  Partial codes, or `platform_absent` for N/A, null otherwise. The lists and
  definitions are built from `coverage.REASON_CODES`. It states once that
  nothing defending a technique makes it a gap, never N/A.
- **The write-back** stores a reason valid for the status. A suggestion whose
  reason is not valid for its status is refused WHOLE, as the PATCH refuses a
  whole request: the row keeps everything it had. The refusal is recorded in
  the `attack.run_ai` audit row as `reason_codes_rejected`, with code-shaped
  values only.
- **The fixture** answers from the prompt: Partial rows carry three of its
  seven codes, and N/A rows carry `platform_absent`.

## Not in this slice

- A row-level or deliverable disclosure of a refused suggestion or a dropped
  reason (#575). The admin audit viewer already shows both lists.
- Requiring a reason, and blocking release on `unable_to_determine`: the
  release-readiness slice (c3).
