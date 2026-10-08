import { expect, test } from "@playwright/test";

import { CLIENT_EMAIL, CLIENT_PASSWORD, signIn } from "../helpers/auth";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";
import { apiExtract } from "../helpers/ai";

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

  // Upload a tiny inventory CSV, then extract. The header is lowercase on
  // purpose: fixture mode names an item from a lowercase `tool`/`name` column
  // only, so a "Tool" header yields no items and one excluded row, a dashboard
  // with nothing on it. One item and no exclusions is the world this spec is
  // about.
  const artifact = await (
    await request.post(`${API_BASE}/artifacts`, {
      headers: H,
      multipart: {
        file: {
          name: "inventory.csv",
          mimeType: "text/csv",
          buffer: Buffer.from("tool,vendor,annual_cost_usd\nWiz,Wiz,100000\n"),
        },
      },
    })
  ).json();

  const ext = await apiExtract(request, H, serviceId, artifact.id);
  const listId = ext.id as string;
  // The fixture's output for that CSV: one item, Wiz, and nothing excluded.
  expect(ext.items.map((i) => i.name)).toEqual(["Wiz"]);
  expect(ext.excluded_rows).toHaveLength(0);

  // Fixture mode drafts no cost, so the consultant enters the inventory's
  // $100,000 while keeping the row, as the review step does.
  for (const item of ext.items) {
    const kept = await request.patch(
      `${API_BASE}/tech-debt/capability-items/${item.id}`,
      { headers: H, data: { disposition: "keep", annual_cost_usd: 100000 } },
    );
    expect(kept.ok(), `keep item: ${await kept.text()}`).toBe(true);
  }

  // #850: approve refuses while a row the AI excluded is unconfirmed. A no-op
  // for this CSV (asserted above); kept so a fixture change that starts
  // excluding the row is confirmed here rather than refused at approve.
  for (const row of ext.excluded_rows) {
    if (row.confirmed === true) continue;
    const confirmed = await request.post(
      `${API_BASE}/tech-debt/capability-lists/${listId}/excluded-rows/${row.index}/confirm`,
      { headers: H },
    );
    expect(
      confirmed.ok(),
      `confirm excluded row: ${await confirmed.text()}`,
    ).toBe(true);
  }

  // Each step asserts its own status, so a refusal names the step that refused
  // instead of surfacing later as a release of an undefined deliverable id.
  const approved = await request.post(
    `${API_BASE}/tech-debt/capability-lists/${listId}/approve`,
    { headers: H },
  );
  expect(approved.ok(), `approve list: ${await approved.text()}`).toBe(true);
  const finalized = await request.post(
    `${API_BASE}/tech-debt/services/${serviceId}/deliverables/finalize`,
    { headers: H },
  );
  expect(
    finalized.ok(),
    `finalize deliverable: ${await finalized.text()}`,
  ).toBe(true);
  const fin = (await finalized.json()) as { id: string };
  const released = await request.post(
    `${API_BASE}/tech-debt/deliverables/${fin.id}/release`,
    { headers: H },
  );
  expect(released.ok(), `release deliverable: ${await released.text()}`).toBe(
    true,
  );

  await signIn(page, CLIENT_EMAIL, CLIENT_PASSWORD);
  await page.goto(`/dashboards/tech-debt/${serviceId}`);

  await expect(page.getByText("Applications", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Annual license spend", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Annual spend by category")).toBeVisible();
  await expect(page.getByText("Full software inventory")).toBeVisible();
  await expect(page.getByPlaceholder(/Search product/i)).toBeVisible();

  // Data, not chrome: the released item reaches the client. Wait on the
  // positive state (the Wiz row) before counting; toHaveText reads
  // textContent, so a CSS uppercase label cannot change it.
  const inventoryRows = page
    .locator("table")
    .filter({ has: page.getByRole("columnheader", { name: "Product" }) })
    .locator("tbody tr");
  await expect(inventoryRows.first().locator("td").first()).toHaveText("Wiz");
  await expect(inventoryRows).toHaveCount(1);
  const kpiValue = (label: string) =>
    page
      .getByText(label, { exact: true })
      .locator("xpath=following-sibling::div[1]");
  await expect(kpiValue("Applications")).toHaveText("1");
  await expect(kpiValue("Annual license spend")).toHaveText("$100,000");

  // The two charts (spend bar + sprawl donut) mount client-side.
  await expect(page.locator("canvas")).toHaveCount(2);

  // A11y (UX finding 19): the dashboards render their own dark shell and used
  // to expose NO <main> at all, so the skip link had no destination and screen
  // readers had no primary content region. Asserted here rather than in s12
  // because this spec already seeds a released dashboard to look at.
  const main = page.locator("main#main-content");
  await expect(main).toHaveCount(1);

  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await skip.press("Enter");
  await expect(page).toHaveURL(/#main-content$/);
  await expect(main).toBeFocused();

  await page.waitForTimeout(1200);
  await page
    .screenshot({ path: "artifacts/tech-debt-dashboard.png", fullPage: true })
    .catch(() => undefined);
});
