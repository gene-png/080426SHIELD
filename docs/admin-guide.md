# Admin guide (Kentro consultant)

> Skeleton — the full consultant guide is still to be written. What follows
> matches the current product; there is no reviewer role (DECISIONS D-023). A
> deliberate release-to-client step exists since Sprint 5 (D-025).

## What an admin does

The Admin (Kentro consultant) is platform-wide and works across client
tenants (picking the active client via the top-nav switcher):

- Creates client tenants and approves their email domains at
  `/admin/management`; verifies the first registrant as the client's Primary
  POC.
- Watches the intake queue (`/admin/queue`) for new submissions.
- Runs the four services (Tech Debt, ZT, CSF, ATT&CK) and the Risk Register
  through their workspaces: uploads inventories, runs AI drafts, curates the
  results (the deterministic engines compute all scores), and generates the
  versioned deliverables.
- Downloads deliverables (spec §15.5 filenames) to hand off to the client.
- Releases deliverables to the client (Sprint 5, D-025): released artifacts
  surface on the client's `/home` dashboard and `/documents` page, and the
  release emails the tenant's active client users (Sprint 7, D-030,
  best-effort — the release stands even if the email fails).
