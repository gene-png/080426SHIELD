import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { acknowledgeOfflineAi } from "../helpers/ai";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";

/**
 * Extraction reconciliation and its review queue (UX finding 4 / E2E F-5).
 *
 * The 2026-08-04 guided review uploaded 21 rows / $1,634,236 and the workspace
 * showed 12 rows / $891,796 with no disclosure at all — the survivors presented
 * as the whole inventory. The fix was to state what came in, what was kept, and
 * what was dropped, and to let a consultant act on the difference.
 *
 * This spec could not be written until now. The fixture extractor invented a
 * name for every unnamed row ("Capability 3"), so it always returned one item
 * per uploaded row, `excluded_rows` was always empty, and neither the banner
 * nor the queue could appear offline. The fixture now skips rows it cannot name
 * — which is what the real prompt instructs — so a CSV containing a note line
 * produces a genuine exclusion.
 *
 * Mints its own service: a shared-DB suite where one spec leans on another's
 * leftovers passes alone and fails in sequence (the s11 defect, now fixed).
 */

// Row 2 carries a note in a column that is not a name field, so the extractor
// has nothing to call it and skips it — exactly one exclusion, deterministic.
const INVENTORY_CSV =
  "name,vendor,category,annual_cost_usd,license_count\n" +
  "CrowdStrike Falcon,CrowdStrike,EDR,120000,500\n" +
  "Splunk Enterprise,Splunk,SIEM,200000,100\n" +
  ",,,,FY26 figures are estimates pending finance sign-off\n" +
  "Okta,Okta,IAM,60000,500\n";

test("the workspace discloses what the extraction dropped, and the row can be recovered", async ({
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
      data: { kind: "tech_debt", title: "E2E Excluded Rows" },
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
  const extractResponse = await extractDone;
  const list = (await extractResponse.json()) as {
    id: string;
    source_rows_total: number;
    items: unknown[];
    excluded_rows: { index: number; summary: string; confirmed: boolean }[];
  };

  // The counts reconcile: nothing is silently missing.
  expect(list.source_rows_total).toBe(4);
  expect(list.items).toHaveLength(3);
  expect(list.excluded_rows).toHaveLength(1);
  expect(
    list.source_rows_total,
    "received must equal included plus excluded",
  ).toBe(list.items.length + list.excluded_rows.length);

  // And the workspace SAYS so, rather than presenting three rows as the whole
  // upload — which is the entire point of the finding.
  const banner = page.getByRole("status", {
    name: "Extraction reconciliation",
  });
  await expect(banner).toBeVisible({ timeout: 30000 });
  await expect(banner).toContainText("4 rows received");
  await expect(banner).toContainText("3 included");
  await expect(banner).toContainText("1 excluded");

  // The dropped row is nameable by a human even though the extractor declined
  // to interpret it. Recovering it keeps the reconciliation honest: it moves
  // from excluded into the list rather than being counted twice.
  const recovered = await request.post(
    `${API_BASE}/tech-debt/capability-lists/${list.id}/excluded-rows/${list.excluded_rows[0].index}/include`,
    {
      headers: H,
      data: {
        name: "Claroty xDome",
        category: "OT Security",
        annual_cost_usd: 133000,
      },
    },
  );
  expect(recovered.ok(), "include excluded row").toBeTruthy();
  const after = (await recovered.json()) as {
    source_rows_total: number;
    items: { name: string }[];
    excluded_rows: unknown[];
  };
  expect(after.items.map((i) => i.name)).toContain("Claroty xDome");
  expect(after.excluded_rows).toHaveLength(0);
  expect(
    after.source_rows_total,
    "the received count never changes — only where the rows went",
  ).toBe(4);
});

test("an exclusion the consultant agrees with stays disclosed, not hidden", async ({
  request,
}) => {
  // Confirming is not deleting. The reconciliation has to keep telling the
  // truth about what was uploaded, so the row stays listed — the workspace just
  // stops flagging it as outstanding.
  test.slow();

  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const H = { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };

  const svc = await (
    await request.post(`${API_BASE}/tech-debt/services`, {
      headers: H,
      data: { kind: "tech_debt", title: "E2E Excluded Rows (confirm)" },
    })
  ).json();

  const artifact = await (
    await request.post(`${API_BASE}/artifacts`, {
      headers: H,
      multipart: {
        file: {
          name: "inventory.csv",
          mimeType: "text/csv",
          buffer: Buffer.from(INVENTORY_CSV),
        },
      },
    })
  ).json();

  const list = await (
    await request.post(
      `${API_BASE}/tech-debt/services/${svc.id}/capability-lists/extract`,
      { headers: H, data: { artifact_id: artifact.id } },
    )
  ).json();
  expect(list.excluded_rows).toHaveLength(1);
  const rowIndex = list.excluded_rows[0].index as number;
  expect(list.excluded_rows[0].confirmed).toBe(false);

  const confirmed = await (
    await request.post(
      `${API_BASE}/tech-debt/capability-lists/${list.id}/excluded-rows/${rowIndex}/confirm`,
      { headers: H },
    )
  ).json();

  // Still listed, still counted — acknowledged, not erased.
  expect(confirmed.excluded_rows).toHaveLength(1);
  expect(confirmed.excluded_rows[0].confirmed).toBe(true);
  expect(confirmed.source_rows_total).toBe(4);
  expect(confirmed.items).toHaveLength(3);
});
