import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { extractAfterUpload, watchUpload } from "../helpers/ai";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";

/**
 * #845, shipped with the Tech Debt v3.2 prompt (for #806): a security tool the
 * extraction marks "not in use" gets its own sign-off group, and confirming it
 * takes it out of the ATT&CK subset.
 *
 * Tech Debt v3.2 returns such a tool `security_related: false` with a note
 * beginning "Security tool not in use:". The offline fixture follows that rule
 * (app/ai/fixtures.py): a security row whose cells say "planned", "not yet
 * deployed", "inactive" or "no longer used". This spec uploads one, so the group
 * is reached offline. It mints its own service, as s37 does, so it does not
 * depend on another spec's leftovers. It was s46 in #869's branch and moved
 * here with the prompt; s46 is taken on main.
 */

// Index 1 is a security row (the fixture's every-4th rule leaves index 3 as the
// only ordinary negative) and its status cell is a lifecycle phrase.
const INVENTORY_CSV =
  "name,vendor,category,annual_cost_usd,license_count,status\n" +
  "CrowdStrike Falcon,CrowdStrike,EDR,120000,500,active\n" +
  "Falcon Identity,CrowdStrike,ITDR,40000,0,planned FY27\n" +
  "Okta,Okta,IAM,60000,500,active\n" +
  "Workday HCM,Workday,HCM,81700,1200,active\n";

const NOT_IN_USE_ROW = "Falcon Identity";

test("a security tool marked not in use is signed off in its own group", async ({
  page,
  request,
}) => {
  test.slow();

  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const H = { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };

  const svc = await (
    await request.post(`${API_BASE}/tech-debt/services`, {
      headers: H,
      data: { kind: "tech_debt", title: "E2E Not In Use Sign-off" },
    })
  ).json();
  const serviceId = svc.id as string;

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto(`/admin/services/${serviceId}/tech-debt`);
  await expect(
    page.getByRole("heading", { name: "Technical Debt Review" }),
  ).toBeVisible({ timeout: 30000 });

  const extractDone = page.waitForResponse(
    (r) =>
      r.url().includes("/capability-lists/extract") &&
      r.request().method() === "POST",
    { timeout: 120000 },
  );
  const uploadWatch = watchUpload(page);
  await page
    .locator('input[type="file"]')
    .first()
    .setInputFiles({
      name: "inventory.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(INVENTORY_CSV),
    });
  await extractAfterUpload(page, extractDone, uploadWatch);

  // 1. Its own group, with its note shown and the approved wording.
  const group = page.getByTestId("security-signoff-not-in-use");
  await expect(group).toBeVisible({ timeout: 30000 });
  await expect(group).toContainText("Security tools not in use (1)");
  await expect(group).toContainText("Note: Security tool not in use:");
  // The ordinary negative is still in today's group.
  await expect(
    page.getByText(/Confirm security classification \(1\)/),
  ).toBeVisible();

  // 2. Confirm: the row leaves the ATT&CK subset (signed off).
  const row = group
    .locator("li", { has: page.getByText(NOT_IN_USE_ROW, { exact: true }) })
    .first();
  const confirmDone = page.waitForResponse(
    (r) =>
      r.url().includes("/security-classification/confirm") &&
      r.request().method() === "POST" &&
      r.ok(),
    { timeout: 60000 },
  );
  await row
    .getByRole("button", { name: "Not in use: remove from ATT&CK" })
    .click();
  await confirmDone;
  await expect(page.getByTestId("security-signoff-not-in-use")).toHaveCount(0, {
    timeout: 15000,
  });

  const after = await (
    await request.get(
      `${API_BASE}/tech-debt/services/${serviceId}/capability-lists/latest`,
      { headers: H },
    )
  ).json();
  const signedOff = (
    after.items as { name: string; security_class_confirmed: boolean }[]
  ).find((i) => i.name === NOT_IN_USE_ROW);
  expect(signedOff!.security_class_confirmed).toBe(true);
});
