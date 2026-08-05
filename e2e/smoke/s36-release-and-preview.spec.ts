import { expect, test, type APIRequestContext } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";

/**
 * Issue 4: the deliverable card is where an analyst both SEES the dashboard and
 * RELEASES it.
 *
 * Before this, finalize produced a PDF and an XLSX and nothing else. The
 * release API existed end-to-end — `releaseZtDeliverable()` and its three
 * siblings were implemented in the web client libs — but had ZERO callers, so
 * no control in the product could satisfy the client dashboards' release gate.
 * A client could therefore never see any dashboard, and an admin could never
 * see one either.
 *
 * These specs seed their own FINALIZED-BUT-UNRELEASED service (mirroring s28,
 * which seeds a released one) because that is exactly the state the issue is
 * about, and the shared seed does not reliably contain it.
 */

test.describe.configure({ timeout: 240_000 });

/** Create a ZT service scored and finalized, deliberately NOT released. */
async function seedFinalizedZt(
  request: APIRequestContext,
  title: string,
): Promise<{ serviceId: string; deliverableId: string }> {
  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const H = { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };

  const svc = await (
    await request.post(`${API_BASE}/zt/services`, {
      headers: H,
      data: { kind: "zero_trust_cisa", title },
    })
  ).json();
  const serviceId = svc.id as string;

  const assess = await (
    await request.post(`${API_BASE}/zt/services/${serviceId}/assessments`, {
      headers: H,
    })
  ).json();
  for (const ans of assess.answers as { id: string }[]) {
    await request.patch(`${API_BASE}/zt/answers/${ans.id}`, {
      headers: H,
      data: { maturity_stage: 2, target_stage: 4 },
    });
  }
  await request.post(`${API_BASE}/zt/assessments/${assess.id}/approve`, {
    headers: H,
  });
  const fin = await request.post(
    `${API_BASE}/zt/services/${serviceId}/deliverables/finalize`,
    { headers: H },
  );
  expect(fin.ok(), "finalize deliverable").toBeTruthy();
  return { serviceId, deliverableId: (await fin.json()).id as string };
}

test("admin: a finalized deliverable card exposes both the dashboard and the release control", async ({
  page,
  request,
}) => {
  const stamp = `${Date.now()}`;
  const { serviceId } = await seedFinalizedZt(request, `E2E Release ${stamp}`);

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto(`/admin/services/${serviceId}/zero-trust-cisa`);

  // The dashboard link — the "somewhere the admin can see the dashboard" that
  // was entirely missing before. Labelled a preview until release.
  const dashboardLink = page
    .getByRole("link", { name: /View dashboard/ })
    .first();
  await expect(dashboardLink).toBeVisible({ timeout: 60_000 });
  await expect(dashboardLink).toHaveAttribute(
    "href",
    `/dashboards/zt/${serviceId}`,
  );
  await expect(dashboardLink).toContainText("preview");

  // The release control exists and is confirm-gated — this is the moment the
  // client can first see the work.
  const releaseButton = page.getByRole("button", { name: "Release to client" });
  await expect(releaseButton).toBeVisible();
  await releaseButton.click();
  await expect(
    page.getByRole("button", { name: "Yes, release" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Yes, release" }).click();

  // After release the card says so, and the preview label is gone.
  await expect(page.getByText(/^Released v\d+$/).first()).toBeVisible({
    timeout: 60_000,
  });
  await expect(
    page.getByRole("link", { name: /View dashboard/ }).first(),
  ).not.toContainText("preview");
});

test("admin: previews the dashboard BEFORE release; the client cannot see it until then", async ({
  page,
  browser,
  request,
}) => {
  const stamp = `${Date.now()}`;
  const { serviceId, deliverableId } = await seedFinalizedZt(
    request,
    `E2E Preview ${stamp}`,
  );

  // Admin: the dashboard renders with real engine figures pre-release.
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto(`/dashboards/zt/${serviceId}`);
  await expect(
    page.getByRole("heading", { name: "Dashboard not available yet" }),
  ).toHaveCount(0, { timeout: 60_000 });
  // Stage 2 of 4 -> 50%: deterministic engine output, not a placeholder.
  await expect(page.getByText("50", { exact: false }).first()).toBeVisible();

  // Client: still gated. The consultant-in-the-loop rule is unchanged.
  const clientCtx = await browser.newContext();
  const clientPage = await clientCtx.newPage();
  await signIn(clientPage, "client@atlas.example", "DemoPass!2026");
  await clientPage.goto(`/dashboards/zt/${serviceId}`);
  await expect(
    clientPage.getByRole("heading", { name: "Dashboard not available yet" }),
  ).toBeVisible({ timeout: 60_000 });

  // Release, and the same client page now renders.
  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const released = await request.post(
    `${API_BASE}/zt/deliverables/${deliverableId}/release`,
    { headers: { Authorization: `Bearer ${token}`, "X-Client-Id": clientId } },
  );
  expect(released.ok(), "release deliverable").toBeTruthy();

  await clientPage.reload();
  await expect(
    clientPage.getByRole("heading", { name: "Dashboard not available yet" }),
  ).toHaveCount(0, { timeout: 60_000 });
  await clientCtx.close();
});
