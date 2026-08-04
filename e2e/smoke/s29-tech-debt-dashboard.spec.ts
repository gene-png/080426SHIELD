import { expect, test } from "@playwright/test";

import { CLIENT_EMAIL, CLIENT_PASSWORD, signIn } from "../helpers/auth";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";

/**
 * D-035: after an admin releases a Tech Debt deliverable, the client can open the
 * software-portfolio dashboard (spend, sprawl, redundancies, inventory). Setup
 * drives the admin API (fixture-mode extraction); the client views via the UI.
 */

test("client views a released software-portfolio dashboard", async ({
  page,
  request,
}) => {
  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const H = { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };

  const svc = await (
    await request.post(`${API_BASE}/tech-debt/services`, {
      headers: H,
      data: { kind: "tech_debt", title: "E2E Software Portfolio" },
    })
  ).json();
  const serviceId = svc.id as string;

  // Upload a tiny inventory CSV, then extract (fixture-mode canned items).
  const artifact = await (
    await request.post(`${API_BASE}/artifacts`, {
      headers: H,
      multipart: {
        file: {
          name: "inventory.csv",
          mimeType: "text/csv",
          buffer: Buffer.from("Tool,Vendor,Annual Cost\nWiz,Wiz,$100000\n"),
        },
      },
    })
  ).json();

  const ext = await (
    await request.post(
      `${API_BASE}/tech-debt/services/${serviceId}/capability-lists/extract`,
      { headers: H, data: { artifact_id: artifact.id } },
    )
  ).json();
  const listId = ext.id as string;
  for (const item of ext.items as { id: string }[]) {
    await request.patch(`${API_BASE}/tech-debt/capability-items/${item.id}`, {
      headers: H,
      data: { disposition: "keep" },
    });
  }

  await request.post(
    `${API_BASE}/tech-debt/capability-lists/${listId}/approve`,
    { headers: H },
  );
  const fin = await (
    await request.post(
      `${API_BASE}/tech-debt/services/${serviceId}/deliverables/finalize`,
      { headers: H },
    )
  ).json();
  const released = await request.post(
    `${API_BASE}/tech-debt/deliverables/${fin.id}/release`,
    { headers: H },
  );
  expect(released.ok(), "release deliverable").toBeTruthy();

  await signIn(page, CLIENT_EMAIL, CLIENT_PASSWORD);
  await page.goto(`/dashboards/tech-debt/${serviceId}`);

  await expect(page.getByText("Applications", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Annual license spend", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Annual spend by category")).toBeVisible();
  await expect(page.getByText("Full software inventory")).toBeVisible();
  await expect(page.getByPlaceholder(/Search product/i)).toBeVisible();

  // The two charts (spend bar + sprawl donut) mount client-side.
  await expect(page.locator("canvas")).toHaveCount(2);

  await page.waitForTimeout(1200);
  await page
    .screenshot({ path: "artifacts/tech-debt-dashboard.png", fullPage: true })
    .catch(() => undefined);
});
