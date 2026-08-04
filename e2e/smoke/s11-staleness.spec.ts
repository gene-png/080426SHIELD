import { expect, test, type Page } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { atlasServiceId } from "../helpers/ids";

/**
 * SMOKE_TEST.md section 11 (T8): the C3 "documents are stale" nudge.
 *
 * Work Order C3 flags an assessment `documents_stale` the moment an AI run
 * changes scores after the deliverable was last generated, and clears the flag
 * when the deliverable is finalised / exported. The admin workspace surfaces
 * that flag as a StaleDocsNudge ("The AI has updated scores since the documents
 * were last generated. Regenerate the deliverable / export to refresh them.").
 *
 * We drive it on the seeded Atlas ATT&CK service because its Run AI needs no
 * Working-Profile seed (unlike CSF) and its run/finalise pair toggles the flag
 * unconditionally (apps/api/app/routes/attack.py:533 sets it, :860 clears it).
 * The seeded assessment is RELEASED (read-only), so we first mint a fresh DRAFT
 * — which starts NOT stale — exactly as s5-attack does.
 *
 * Assertions read the flag through a full page reload (committed-DB truth),
 * which the s5/s6 race notes established as the robust signal under next-dev +
 * React StrictMode double-loads.
 */

const NUDGE = /updated scores since the documents were last generated/i;

/**
 * Sign in, open the workspace, layer a fresh (non-stale) draft on top, and
 * return the resolved Atlas ATT&CK service id (the test body reuses it).
 */
async function openFreshDraft(page: Page): Promise<string> {
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  // Seeded Atlas Defense "MITRE ATT&CK Coverage" service (scripts/seed_demo.py),
  // the same service s5-attack drives.
  const attackServiceId = await atlasServiceId(page, "attack_coverage");
  await page.goto(`/admin/services/${attackServiceId}/attack-coverage`);
  // The header only renders once EnsureActiveClient has aligned the
  // active-client cookie to Atlas, so the proxy POST below is tenant-scoped.
  await expect(
    page.getByRole("heading", { name: "MITRE ATT&CK Coverage" }),
  ).toBeVisible({ timeout: 30000 });

  // Discard any open draft first, then mint. SPRINT_3 T1 added a draft-exists
  // guard: POST now REUSES an open draft instead of minting a new version, so a
  // plain POST would hand back the draft s5-attack left on this same service —
  // one that already had an AI run and so already shows the stale nudge,
  // breaking the "brand-new draft has no nudge" precondition below. Discarding
  // throws any open DRAFT away (Sprint 9 T0 / D-031; ignored when nothing is
  // open), so the following POST cuts a genuinely fresh, never-AI-run draft.
  const prior = await page.request.get(
    `/api/proxy/attack/services/${attackServiceId}/assessments/latest`,
  );
  if (prior.ok()) {
    const p = (await prior.json()) as { id: string; status: string };
    if (p.status === "draft") {
      await page.request.post(`/api/proxy/attack/assessments/${p.id}/discard`);
    }
  }
  const created = await page.request.post(
    `/api/proxy/attack/services/${attackServiceId}/assessments`,
  );
  expect(created.ok()).toBeTruthy();

  await page.reload();
  await expect(page.getByText(/Draft v\d+/)).toBeVisible({ timeout: 30000 });
  await page.waitForLoadState("networkidle").catch(() => undefined);
  return attackServiceId;
}

/** Click Run AI and wait for the run-ai POST to resolve. */
async function runAi(page: Page): Promise<void> {
  const runDone = page.waitForResponse(
    (r) =>
      r.url().includes("/attack/services/") &&
      r.url().includes("/run-ai") &&
      r.request().method() === "POST" &&
      r.ok(),
    { timeout: 90000 },
  );
  await page.getByRole("button", { name: "Run AI" }).click();
  await runDone;
}

test("Run AI raises the stale-documents nudge; finalising the deliverable clears it", async ({
  page,
}) => {
  // Long flow (sign-in + mint + run + approve + finalise + two reloads) against
  // a next-dev server shared with the other smoke specs; triple the budget.
  test.slow();
  const attackServiceId = await openFreshDraft(page);

  // A brand-new draft has never had an AI run, so the nudge is absent.
  await expect(page.getByText(NUDGE)).toHaveCount(0);

  // Run AI changes scores, which sets documents_stale = true (C3).
  await runAi(page);

  // Assert the persisted flag through a fresh load: the workspace now renders
  // the regenerate nudge.
  await page.reload();
  await expect(page.getByText(/Draft v\d+/)).toBeVisible({ timeout: 60000 });
  await expect(page.getByText(NUDGE)).toBeVisible({ timeout: 30000 });

  // Finalising the deliverable refreshes the documents and clears the flag.
  // Approve is a precondition for finalise; both go through the same proxy
  // endpoints the workspace's own Approve/Finalize buttons call, so this is a
  // faithful exercise of the clear path without re-testing s7's export UI.
  const latest = await page.request.get(
    `/api/proxy/attack/services/${attackServiceId}/assessments/latest`,
  );
  expect(latest.ok()).toBeTruthy();
  const assessmentId = ((await latest.json()) as { id: string }).id;

  const approved = await page.request.post(
    `/api/proxy/attack/assessments/${assessmentId}/approve`,
  );
  expect(approved.ok()).toBeTruthy();

  const finalized = await page.request.post(
    `/api/proxy/attack/services/${attackServiceId}/deliverables/finalize`,
  );
  expect(finalized.ok()).toBeTruthy();

  // On reload the flag is cleared, so the nudge is gone.
  await page.reload();
  await expect(page.getByText(/v\d+/).first()).toBeVisible({ timeout: 60000 });
  await expect(page.getByText(NUDGE)).toHaveCount(0);
});
