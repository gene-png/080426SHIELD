import { expect, test } from "@playwright/test";

import { CLIENT_EMAIL, CLIENT_PASSWORD, signIn } from "../helpers/auth";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";

/**
 * D-035: after an admin releases a Zero Trust deliverable, the client can open an
 * interactive maturity dashboard (current-vs-target radar + per-pillar deep
 * dive). Setup drives the admin API; the client views through the real UI.
 */

test("client views a released Zero Trust maturity dashboard", async ({
  page,
  request,
}) => {
  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const H = { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };

  const svc = await (
    await request.post(`${API_BASE}/zt/services`, {
      headers: H,
      data: { kind: "zero_trust_cisa", title: "E2E Zero Trust Dashboard" },
    })
  ).json();
  const serviceId = svc.id as string;

  const assess = await (
    await request.post(`${API_BASE}/zt/services/${serviceId}/assessments`, {
      headers: H,
    })
  ).json();
  const answers = assess.answers as { id: string }[];
  for (const ans of answers) {
    await request.patch(`${API_BASE}/zt/answers/${ans.id}`, {
      headers: H,
      data: { maturity_stage: 2, target_stage: 4 },
    });
  }

  await request.post(`${API_BASE}/zt/assessments/${assess.id}/approve`, {
    headers: H,
  });
  const fin = await (
    await request.post(
      `${API_BASE}/zt/services/${serviceId}/deliverables/finalize`,
      { headers: H },
    )
  ).json();
  const released = await request.post(
    `${API_BASE}/zt/deliverables/${fin.id}/release`,
    { headers: H },
  );
  expect(released.ok(), "release deliverable").toBeTruthy();

  await signIn(page, CLIENT_EMAIL, CLIENT_PASSWORD);
  await page.goto(`/dashboards/zt/${serviceId}`);

  await expect(
    page.getByText("Current maturity", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Target maturity", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Maturity across the model")).toBeVisible();
  await expect(page.getByText("Per-pillar deep dive")).toBeVisible();

  // The radar chart mounts client-side via a dynamic Chart.js import.
  await expect(page.locator("canvas")).toHaveCount(1);

  await page.waitForTimeout(1200);
  await page
    .screenshot({ path: "artifacts/zt-dashboard.png", fullPage: true })
    .catch(() => undefined);
});
