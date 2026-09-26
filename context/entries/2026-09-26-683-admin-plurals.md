# 2026-09-26: three admin sentences agree in number with their counts (#683)

Branch `track2/admin-plural-number`, from `main` at `e602542`. The admin
twins of #452's shape (a fixed plural over a count or list that can be one):

- `IntakeQueue.tsx`: "hides all 1 requests" becomes "hides the 1 request.
  Clear the filters to see it."
- `RiskRegisterDashboard.tsx`: the excluded-inputs banner says "That
  assessment exists … approving it if it should be included" for one.
- `AttackCitationAccounting.tsx`: after "1 technique was left unresolved", it
  now says "It stays held out … answers that field, or set its tools
  yourself".

Tests: singular and plural for each, through the component. Each copy revert
turns its singular test red. Existing assertions pass unchanged.

**An existing test file's mock changed** (the coordinator's verdict, asked
first): `IntakeQueue.test.tsx` mocked `useServiceStages` with `stages: []`
and a `reload` field. The real hook returns `stages: ServiceStages | null`
and has no `reload`. No existing test rendered a request row, so the
unreachable shape was never exercised. Now `stages: null`, typed with
`satisfies ReturnType<typeof useServiceStages>`, which is what caught the
phantom `reload`. The file's 20 existing tests pass identically before and
after.

Admin screens only: no client reads them.
