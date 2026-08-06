import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";
import { acknowledgeOfflineAi } from "../helpers/ai";

/**
 * SMOKE_TEST.md section 11 (T8): the C3 "documents are stale" nudge.
 *
 * Work Order C3 flags an assessment `documents_stale` the moment an AI run
 * changes scores after the deliverable was last generated, and clears the flag
 * when the deliverable is finalised / exported. The admin workspace surfaces
 * that flag as a StaleDocsNudge ("The AI has updated scores since the documents
 * were last generated. Regenerate the deliverable / export to refresh them.").
 *
 * ATT&CK is the vehicle because its Run AI needs no Working-Profile seed
 * (unlike CSF) and its run/finalise pair toggles the flag unconditionally
 * (apps/api/app/routes/attack.py:533 sets it, :860 clears it).
 *
 * THIS SPEC MINTS ITS OWN SERVICE. It used to share the seeded Atlas ATT&CK
 * service with s5-attack, discarding whatever draft it found and cutting a new
 * one — which is order-dependent twice over: s5 and this spec raced for the
 * same service, and this spec then APPROVES and FINALISES it, changing the
 * state every later spec inherits. It passed alone and failed in sequence, the
 * exact shape CLAUDE.md warns about. A private service removes the coupling
 * entirely, the way s29 and s33 already do.
 *
 * Assertions read the flag through a full page reload (committed-DB truth),
 * which the s5/s6 race notes established as the robust signal under next-dev +
 * React StrictMode double-loads.
 */

const NUDGE = /updated scores since the documents were last generated/i;

/**
 * Sign in, mint a PRIVATE ATT&CK service, open its workspace with a fresh
 * (never-AI-run, so never-stale) draft, and return the service id.
 */
async function openFreshDraft(
  page: Page,
  request: APIRequestContext,
): Promise<string> {
  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const svc = await (
    await request.post(`${API_BASE}/attack/services`, {
      headers: { Authorization: `Bearer ${token}`, "X-Client-Id": clientId },
      data: { kind: "attack_coverage", title: "E2E Staleness Nudge" },
    })
  ).json();
  const attackServiceId = svc.id as string;

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto(`/admin/services/${attackServiceId}/attack-coverage`);
  // The header only renders once EnsureActiveClient has aligned the
  // active-client cookie to Atlas, so the proxy POST below is tenant-scoped.
  await expect(
    page.getByRole("heading", { name: "MITRE ATT&CK Coverage" }),
  ).toBeVisible({ timeout: 30000 });

  // The service is ours and brand new, so there is no prior draft to discard —
  // the discard dance this spec used to perform existed only to undo whatever
  // s5-attack had left behind on the shared service.
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
  // The offline guard intercepts the first click when no key is loaded.
  await acknowledgeOfflineAi(page);
  await runDone;
}

test("Run AI raises the stale-documents nudge; finalising the deliverable clears it", async ({
  page,
  request,
}) => {
  // Long flow (sign-in + mint + run + approve + finalise + two reloads) against
  // a next-dev server shared with the other smoke specs; triple the budget.
  test.slow();
  const attackServiceId = await openFreshDraft(page, request);

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
