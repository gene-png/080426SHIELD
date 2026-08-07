import { expect, test, type APIRequestContext } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { adminApiToken, API_BASE } from "../helpers/ids";

/**
 * IA appendix: "Deliverables — draft, approved, generated and released
 * products; version history and client-visible status."
 *
 * Deliverables were only visible one service workspace at a time, so an admin
 * answering "what have we produced, and what has the client actually seen?" had
 * to open every workspace in turn.
 *
 * This spec SEEDS ITS OWN unreleased deliverable rather than hoping the shared
 * seed happens to contain one. `s34` taught that lesson the hard way: its
 * Run-AI-guard test self-skipped whenever the seeded ATT&CK assessment was
 * already released, so whether the assertion ran at all depended on database
 * state nobody controls — and a spec that skips is untested, not passing. The
 * unreleased row is the entire point of this surface, so it must be guaranteed.
 */

test.describe.configure({ timeout: 180_000 });

interface Row {
  id: string;
}

function headers(token: string, clientId: string): Record<string, string> {
  return { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };
}

/** A throwaway tenant, so this never perturbs the seeded Atlas engagement. */
async function createTenant(
  request: APIRequestContext,
  token: string,
): Promise<string> {
  const res = await request.post(`${API_BASE}/admin/clients`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { legal_name: `Deliverables QA ${Date.now()}` },
  });
  expect(res.ok(), `create tenant (${res.status()})`).toBeTruthy();
  return ((await res.json()) as Row).id;
}

/** Finalize a CSF deliverable WITHOUT releasing it. */
async function finalizeUnreleased(
  request: APIRequestContext,
  h: Record<string, string>,
): Promise<void> {
  const svc = await request.post(`${API_BASE}/csf/services`, {
    headers: h,
    data: { kind: "nist_csf", title: `Deliverables QA CSF ${Date.now()}` },
  });
  expect(svc.ok(), `open CSF service (${svc.status()})`).toBeTruthy();
  const serviceId = ((await svc.json()) as Row).id;

  const assessment = await request.post(
    `${API_BASE}/csf/services/${serviceId}/assessments`,
    { headers: h },
  );
  expect(
    assessment.ok(),
    `create assessment (${assessment.status()})`,
  ).toBeTruthy();
  const assessmentId = ((await assessment.json()) as Row).id;

  const approve = await request.post(
    `${API_BASE}/csf/assessments/${assessmentId}/approve`,
    { headers: h },
  );
  expect(approve.ok(), `approve (${approve.status()})`).toBeTruthy();

  const fin = await request.post(
    `${API_BASE}/csf/services/${serviceId}/deliverables/finalize`,
    { headers: h },
  );
  expect(fin.status(), `finalize (${await fin.text()})`).toBe(201);
  // Deliberately NOT released — that is the row this surface must show.
}

test("admin deliverables: an unreleased report is listed and marked not client-visible", async ({
  page,
  request,
}) => {
  test.slow();
  const token = await adminApiToken(request);
  const clientId = await createTenant(request, token);
  await finalizeUnreleased(request, headers(token, clientId));

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  const switched = await page.request.post("/api/active-client", {
    data: { clientId },
  });
  expect(switched.ok(), "align active client to the QA tenant").toBeTruthy();

  await page.goto("/admin/deliverables");
  await expect(page.getByRole("heading", { name: "Deliverables" })).toBeVisible(
    {
      timeout: 30_000,
    },
  );

  // The unreleased row is present and honest about not being client-visible.
  await expect(page.getByText("Generated", { exact: true })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText(/0 visible to the client/)).toBeVisible({
    timeout: 30_000,
  });

  // Read-only: release stays in the workspace that owns the service.
  await expect(
    page.getByRole("button", { name: /Release/ }),
    "the cross-service list must not offer release actions",
  ).toHaveCount(0);
});

test("admin deliverables: reachable from the admin sidebar", async ({
  page,
}) => {
  test.slow();
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin/queue");

  const navLink = page
    .getByRole("link", { name: "Deliverables", exact: true })
    .first();
  await expect(navLink).toBeVisible({ timeout: 30_000 });
  await navLink.click();

  await expect
    .poll(() => new URL(page.url()).pathname, { timeout: 30_000 })
    .toBe("/admin/deliverables");
  // 30s, not the 10s default: arriving here is the FIRST hit on this route in a
  // CI run, so next dev compiles it cold. The URL poll above already passed when
  // this failed in CI — navigation was fine, the page just had not finished
  // building inside 10 seconds. Every other wait in this file is 30s; this one
  // defaulted by oversight.
  await expect(page.getByRole("heading", { name: "Deliverables" })).toBeVisible(
    { timeout: 30_000 },
  );
});
