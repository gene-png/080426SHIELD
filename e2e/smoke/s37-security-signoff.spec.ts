import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { acknowledgeOfflineAi } from "../helpers/ai";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";

/**
 * Sign-off queue for negative security classifications (migration 0038).
 *
 * Tech Debt covers the whole software portfolio, so the AI classifies each row
 * rather than dropping the non-security ones. That classification decides what
 * the ATT&CK mapping may cite — and `valid_tools` in routes/attack.py is a hard
 * allow-list, so a tool wrongly marked non-security becomes UNCITABLE and the
 * technique it covers reads as uncovered rather than unassessed.
 *
 * A negative is therefore provisional until a consultant agrees. This spec
 * proves the whole loop through the UI: the queue appears, the row is still in
 * the ATT&CK subset while unconfirmed, sign-off removes it, and an overturn
 * puts it back.
 *
 * This spec MINTS ITS OWN SERVICE rather than reusing the seeded one. The suite
 * is serialized against a shared DB, and a spec that depends on another spec's
 * leftovers passes alone and fails in sequence — the s11-staleness defect.
 *
 * Reachable offline only because the fixture extractor classifies every 4th row
 * as not security-related (app/ai/fixtures.py). Before that it echoed every row
 * as security tooling, so this queue could never appear in fixture mode and the
 * surface was untestable — the same hole the excluded-rows queue still has.
 */

// Four rows: the fixture marks index 3 (Workday HCM) as not security-related,
// so exactly one sign-off is pending and the assertions stay deterministic.
const INVENTORY_CSV =
  "name,vendor,category,annual_cost_usd,license_count\n" +
  "CrowdStrike Falcon,CrowdStrike,EDR,120000,500\n" +
  "Splunk Enterprise,Splunk,SIEM,200000,100\n" +
  "Okta,Okta,IAM,60000,500\n" +
  "Workday HCM,Workday,HCM,81700,1200\n";

const NON_SECURITY_ROW = "Workday HCM";

test("an unconfirmed 'not security' call is provisional; sign-off is what removes it", async ({
  page,
  request,
}) => {
  // Upload + extraction against a next-dev server serving the rest of the
  // suite; requests queue for tens of seconds under load.
  test.slow();

  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const H = { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };

  const svc = await (
    await request.post(`${API_BASE}/tech-debt/services`, {
      headers: H,
      data: { kind: "tech_debt", title: "E2E Security Sign-off" },
    })
  ).json();
  const serviceId = svc.id as string;

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto(`/admin/services/${serviceId}/tech-debt`);
  await expect(
    page.getByRole("heading", { name: "Technical Debt Review" }),
  ).toBeVisible({ timeout: 30000 });

  // Extract through the UI so the offline Run-AI guard is exercised too.
  const extractDone = page.waitForResponse(
    (r) =>
      r.url().includes("/capability-lists/extract") &&
      r.request().method() === "POST",
    { timeout: 120000 },
  );
  await page
    .locator('input[type="file"]')
    .first()
    .setInputFiles({
      name: "inventory.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(INVENTORY_CSV),
    });
  const extractBtn = page
    .getByRole("button", { name: "Extract from this" })
    .first();
  if (await extractBtn.isVisible().catch(() => false)) {
    await extractBtn.click();
    await acknowledgeOfflineAi(page);
  }
  await extractDone;

  // 1. The queue surfaces the negative call, and says how many are outstanding.
  await expect(
    page.getByText(/Confirm security classification \(1\)/),
  ).toBeVisible({ timeout: 30000 });

  const queueCard = page
    .locator("li", { has: page.getByText(NON_SECURITY_ROW, { exact: true }) })
    .first();
  await expect(queueCard).toBeVisible();

  // 2. THE SAFEGUARD: while unconfirmed, the row is still offered to ATT&CK.
  //    Asserted against the API because the allow-list is server-side — the
  //    workspace cannot show what the mapping is permitted to cite.
  const beforeItems = await (
    await request.get(
      `${API_BASE}/tech-debt/services/${serviceId}/capability-lists/latest`,
      { headers: H },
    )
  ).json();
  const workday = (
    beforeItems.items as {
      id: string;
      name: string;
      security_related: boolean | null;
      security_class_confirmed: boolean;
    }[]
  ).find((i) => i.name === NON_SECURITY_ROW);
  expect(
    workday,
    `${NON_SECURITY_ROW} must be extracted, not dropped`,
  ).toBeTruthy();
  expect(workday!.security_related).toBe(false);
  // Not signed off, so the negative has not been acted on.
  expect(workday!.security_class_confirmed).toBe(false);

  // 3. Sign off. Only now does the row leave the ATT&CK subset.
  const confirmDone = page.waitForResponse(
    (r) =>
      r.url().includes("/security-classification/confirm") &&
      r.request().method() === "POST" &&
      r.ok(),
    { timeout: 60000 },
  );
  await queueCard.getByRole("button", { name: /Not security/ }).click();
  await confirmDone;

  // The queue empties — nothing outstanding, so the card goes away entirely.
  await expect(page.getByText(/Confirm security classification/)).toHaveCount(
    0,
    { timeout: 15000 },
  );

  const afterConfirm = await (
    await request.get(
      `${API_BASE}/tech-debt/services/${serviceId}/capability-lists/latest`,
      { headers: H },
    )
  ).json();
  const confirmed = (
    afterConfirm.items as { name: string; security_class_confirmed: boolean }[]
  ).find((i) => i.name === NON_SECURITY_ROW);
  expect(confirmed!.security_class_confirmed).toBe(true);
});

test("a wrongly-classified security tool can be overturned back into scope", async ({
  page,
  request,
}) => {
  // The Claroty-shaped case from the 2026-08-04 review: OT security tooling the
  // model does not recognise as security. Recovering it must be possible, and
  // must clear the sign-off so a stale flag cannot re-exclude it later.
  test.slow();

  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const H = { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };

  const svc = await (
    await request.post(`${API_BASE}/tech-debt/services`, {
      headers: H,
      data: { kind: "tech_debt", title: "E2E Security Overturn" },
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
  await page
    .locator('input[type="file"]')
    .first()
    .setInputFiles({
      name: "inventory.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(INVENTORY_CSV),
    });
  const extractBtn = page
    .getByRole("button", { name: "Extract from this" })
    .first();
  if (await extractBtn.isVisible().catch(() => false)) {
    await extractBtn.click();
    await acknowledgeOfflineAi(page);
  }
  await extractDone;

  const queueCard = page
    .locator("li", { has: page.getByText(NON_SECURITY_ROW, { exact: true }) })
    .first();
  await expect(queueCard).toBeVisible({ timeout: 30000 });

  // "Mark security-related" stays disabled until a function is named: a
  // capability that serves none of prevent/detect/respond is not a claim the
  // ATT&CK mapping can act on, and the API rejects it with a 422.
  const overturn = queueCard.getByRole("button", {
    name: "Mark security-related",
  });
  await expect(overturn).toBeDisabled();

  await queueCard.getByRole("checkbox", { name: /detect/i }).check();
  await expect(overturn).toBeEnabled();

  const overrideDone = page.waitForResponse(
    (r) =>
      r.url().includes("/security-classification/override") &&
      r.request().method() === "POST" &&
      r.ok(),
    { timeout: 60000 },
  );
  await overturn.click();
  await overrideDone;

  await expect(page.getByText(/Confirm security classification/)).toHaveCount(
    0,
    { timeout: 15000 },
  );

  const after = await (
    await request.get(
      `${API_BASE}/tech-debt/services/${serviceId}/capability-lists/latest`,
      { headers: H },
    )
  ).json();
  const row = (
    after.items as {
      name: string;
      security_related: boolean | null;
      security_functions: string[];
      security_class_confirmed: boolean;
    }[]
  ).find((i) => i.name === NON_SECURITY_ROW);
  expect(row!.security_related).toBe(true);
  expect(row!.security_functions).toEqual(["detect"]);
  // The overturn clears the sign-off — a stale confirmation must not survive.
  expect(row!.security_class_confirmed).toBe(false);
});
